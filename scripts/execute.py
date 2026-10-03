#!/usr/bin/env python3
"""
Harness Step Executor — phase 내 step을 순차 실행하고 자가 교정한다.

Usage:
    python3 scripts/execute.py <phase-dir> [--push]
"""

import argparse
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

# AC는 hook을 거치지 않고 실행되므로 Bash 가드와 같은 기준으로 미리 검사한다.
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
from bash_guard import find_danger  # noqa: E402

AC_HEADER = re.compile(r"^##\s+Acceptance Criteria\s*$")
SECTION_END = re.compile(r"^#{1,2}\s")
FENCE = re.compile(r"^\s*(`{3,})\s*(\S*)")


@contextlib.contextmanager
def progress_indicator(label: str):
    """터미널 진행 표시기. with 문으로 사용하며 .elapsed 로 경과 시간을 읽는다."""
    frames = "◐◓◑◒"
    stop = threading.Event()
    t0 = time.monotonic()

    def _animate():
        idx = 0
        while not stop.wait(0.12):
            sec = int(time.monotonic() - t0)
            sys.stderr.write(f"\r{frames[idx % len(frames)]} {label} [{sec}s]")
            sys.stderr.flush()
            idx += 1
        sys.stderr.write("\r" + " " * (len(label) + 20) + "\r")
        sys.stderr.flush()

    th = threading.Thread(target=_animate, daemon=True)
    th.start()
    info = types.SimpleNamespace(elapsed=0.0)
    try:
        yield info
    finally:
        stop.set()
        th.join()
        info.elapsed = time.monotonic() - t0


class StepExecutor:
    """Phase 디렉토리 안의 step들을 순차 실행하는 하네스."""

    MAX_RETRIES = 3
    AC_TIMEOUT = 600
    AGENT_FIELDS = ("status", "summary", "error_message", "blocked_reason")
    FEAT_MSG = "feat({phase}): step {num} — {name}"
    CHORE_MSG = "chore({phase}): step {num} output"
    TZ = timezone(timedelta(hours=9))

    def __init__(self, phase_dir_name: str, *, auto_push: bool = False):
        self._root = str(ROOT)
        self._phases_dir = ROOT / "phases"
        self._phase_dir = self._phases_dir / phase_dir_name
        self._phase_dir_name = phase_dir_name
        self._top_index_file = self._phases_dir / "index.json"
        self._auto_push = auto_push

        if not self._phase_dir.is_dir():
            print(f"ERROR: {self._phase_dir} not found")
            sys.exit(1)

        self._index_file = self._phase_dir / "index.json"
        if not self._index_file.exists():
            print(f"ERROR: {self._index_file} not found")
            sys.exit(1)

        idx = self._read_json(self._index_file)
        self._project = idx.get("project", "project")
        self._phase_name = idx.get("phase", phase_dir_name)
        self._total = len(idx["steps"])

    def run(self):
        self._print_header()
        self._check_tools()
        self._check_blockers()
        self._checkout_branch()
        guardrails = self._load_guardrails()
        self._load_acs()
        self._ensure_created_at()
        self._execute_all_steps(guardrails)
        self._finalize()

    # --- timestamps ---

    def _stamp(self) -> str:
        return datetime.now(self.TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

    # --- JSON I/O ---

    @staticmethod
    def _read_json(p: Path) -> dict:
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(p: Path, data: dict):
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- git ---

    def _run_git(self, *args) -> subprocess.CompletedProcess:
        cmd = ["git"] + list(args)
        return subprocess.run(cmd, cwd=self._root, capture_output=True, text=True)

    def _checkout_branch(self):
        branch = f"feat-{self._phase_name}"

        r = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if r.returncode != 0:
            print(f"  ERROR: git을 사용할 수 없거나 git repo가 아닙니다.")
            print(f"  {r.stderr.strip()}")
            sys.exit(1)

        if r.stdout.strip() == branch:
            return

        r = self._run_git("rev-parse", "--verify", branch)
        r = self._run_git("checkout", branch) if r.returncode == 0 else self._run_git("checkout", "-b", branch)

        if r.returncode != 0:
            print(f"  ERROR: 브랜치 '{branch}' checkout 실패.")
            print(f"  {r.stderr.strip()}")
            print(f"  Hint: 변경사항을 stash하거나 commit한 후 다시 시도하세요.")
            sys.exit(1)

        print(f"  Branch: {branch}")

    def _head(self) -> str:
        return self._run_git("rev-parse", "HEAD").stdout.strip()

    def _undo_agent_commits(self, head: str):
        """에이전트가 만든 커밋을 되돌린다. 변경 내용은 working tree에 남고, 판정은 게이트가 한다."""
        if self._head() != head:
            self._run_git("reset", "--soft", head)
            print(f"  WARN: 에이전트가 커밋해서 reset --soft {head[:7]}로 되돌렸습니다. 변경 내용은 working tree에 남아 있습니다.")

    def _commit_step(self, step_num: int, step_name: str):
        output_rel = f"phases/{self._phase_dir_name}/step{step_num}-output.json"
        index_rel = f"phases/{self._phase_dir_name}/index.json"

        self._run_git("add", "-A")
        self._run_git("reset", "HEAD", "--", output_rel)
        self._run_git("reset", "HEAD", "--", index_rel)

        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.FEAT_MSG.format(phase=self._phase_name, num=step_num, name=step_name)
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  Commit: {msg}")
            else:
                print(f"  WARN: 코드 커밋 실패: {r.stderr.strip()}")

        self._run_git("add", "-A")
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.CHORE_MSG.format(phase=self._phase_name, num=step_num)
            r = self._run_git("commit", "-m", msg)
            if r.returncode != 0:
                print(f"  WARN: housekeeping 커밋 실패: {r.stderr.strip()}")

    # --- top-level index ---

    def _update_top_index(self, status: str):
        if not self._top_index_file.exists():
            return
        top = self._read_json(self._top_index_file)
        ts = self._stamp()
        for phase in top.get("phases", []):
            if phase.get("dir") == self._phase_dir_name:
                phase["status"] = status
                ts_key = {"completed": "completed_at", "error": "failed_at", "blocked": "blocked_at"}.get(status)
                if ts_key:
                    phase[ts_key] = ts
                break
        self._write_json(self._top_index_file, top)

    # --- guardrails & context ---

    def _load_guardrails(self) -> str:
        sections = []
        claude_md = ROOT / "CLAUDE.md"
        if claude_md.exists():
            sections.append(f"## 프로젝트 규칙 (CLAUDE.md)\n\n{claude_md.read_text()}")
        docs_dir = ROOT / "docs"
        if docs_dir.is_dir():
            for doc in sorted(docs_dir.glob("*.md")):
                sections.append(f"## {doc.stem}\n\n{doc.read_text()}")
        return "\n\n---\n\n".join(sections) if sections else ""

    @staticmethod
    def _build_step_context(index: dict) -> str:
        lines = [
            f"- Step {s['step']} ({s['name']}): {s['summary']}"
            for s in index["steps"]
            if s["status"] == "completed" and s.get("summary")
        ]
        if not lines:
            return ""
        return "## 이전 Step 산출물\n\n" + "\n".join(lines) + "\n\n"

    def _build_preamble(self, guardrails: str, step_context: str,
                        prev_error: Optional[str] = None) -> str:
        retry_section = ""
        if prev_error:
            retry_section = (
                f"\n## ⚠ 이전 시도 실패 — 아래 에러를 반드시 참고하여 수정하라\n\n"
                f"{prev_error}\n\n---\n\n"
            )
        return (
            f"당신은 {self._project} 프로젝트의 개발자입니다. 아래 step을 수행하세요.\n\n"
            f"{guardrails}\n\n---\n\n"
            f"{step_context}{retry_section}"
            f"## 작업 규칙\n\n"
            f"1. 이전 step에서 작성된 코드를 확인하고 일관성을 유지하라.\n"
            f"2. 이 step에 명시된 작업만 수행하라. 추가 기능이나 파일을 만들지 마라.\n"
            f"3. 기존 테스트를 깨뜨리지 마라.\n"
            f"4. AC(Acceptance Criteria) 검증을 직접 실행하라.\n"
            f"5. /phases/{self._phase_dir_name}/index.json의 해당 step status를 업데이트하라:\n"
            f"   - AC 통과 → \"completed\" + \"summary\" 필드에 이 step의 산출물을 한 줄로 요약. "
            f"completed를 기록하면 실행기가 AC로 다시 검증한다.\n"
            f"   - AC를 통과시키지 못함 → \"error\" + \"error_message\"에 구체적인 원인 기록\n"
            f"   - 사용자 개입이 필요한 경우 (API 키, 인증, 수동 설정 등) → \"blocked\" + \"blocked_reason\" 기록 후 즉시 중단\n"
            f"6. 커밋하지 마라. 실행기가 검증한 뒤 커밋한다.\n"
            f"7. AC 블록, docs/, CLAUDE.md, 다른 step의 상태를 수정하지 마라.\n\n---\n\n"
        )

    # --- Claude 호출 ---

    def _invoke_claude(self, step: dict, preamble: str) -> dict:
        step_num, step_name = step["step"], step["name"]
        step_file = self._phase_dir / f"step{step_num}.md"

        if not step_file.exists():
            print(f"  ERROR: {step_file} not found")
            sys.exit(1)

        prompt = preamble + step_file.read_text()
        result = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", "--output-format", "json", prompt],
            cwd=self._root, capture_output=True, text=True, timeout=1800,
        )

        if result.returncode != 0:
            print(f"\n  WARN: Claude가 비정상 종료됨 (code {result.returncode})")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")

        output = {
            "step": step_num, "name": step_name,
            "exitCode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
        }
        out_path = self._phase_dir / f"step{step_num}-output.json"
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        return output

    # --- AC 계약 ---

    @staticmethod
    def _extract_ac(md: str) -> str:
        """`## Acceptance Criteria` 섹션의 ```bash 블록 하나를 꺼낸다. 계약 위반이면 ValueError."""
        lines = md.splitlines()
        start = next((i for i, line in enumerate(lines) if AC_HEADER.match(line.strip())), None)
        if start is None:
            raise ValueError("'## Acceptance Criteria' 헤더가 없습니다")

        blocks, fence, body = [], None, []
        for line in lines[start + 1:]:
            m = FENCE.match(line)
            if fence is None:
                if SECTION_END.match(line):
                    break
                if m:
                    fence, body = m.groups(), []
            elif m and not m.group(2) and len(m.group(1)) >= len(fence[0]):
                if fence[1] == "bash":
                    blocks.append("\n".join(body).strip("\n"))
                fence = None
            else:
                body.append(line)

        if fence is not None:
            raise ValueError("코드 블록이 닫히지 않았습니다")
        if len(blocks) != 1:
            raise ValueError(f"```bash 블록이 {len(blocks)}개입니다 (정확히 1개여야 함)")
        ac = blocks[0]
        if not any(line.strip() and not line.strip().startswith("#") for line in ac.splitlines()):
            raise ValueError("```bash 블록이 비어 있습니다")
        danger = find_danger(ac)
        if danger:
            raise ValueError(f"위험한 명령이 있습니다 ({danger})")
        return ac

    def _load_acs(self):
        """확정되지 않은 모든 step의 AC를 검사하고 고정한다. 오류는 모아서 한 번에 보고한다."""
        self._acs, errors = {}, []
        for s in self._read_json(self._index_file)["steps"]:
            if self._confirmed(s):
                continue
            step_file = self._phase_dir / f"step{s['step']}.md"
            try:
                self._acs[s["step"]] = self._extract_ac(step_file.read_text(encoding="utf-8"))
            except FileNotFoundError:
                errors.append(f"Step {s['step']} ({s['name']}): {step_file.name} 파일이 없습니다")
            except ValueError as e:
                errors.append(f"Step {s['step']} ({s['name']}): {e}")

        if errors:
            print("\n  ERROR: AC 계약 위반. step 파일을 고친 뒤 다시 실행하세요.")
            for e in errors:
                print(f"    - {e}")
            sys.exit(1)

    # --- AC 게이트 ---

    def _run_ac(self, ac: str) -> dict:
        """AC를 bash -e -o pipefail -x로 실행한다. 끝나면 항상 프로세스 그룹 전체를 종료한다."""
        t0 = time.monotonic()
        try:
            proc = subprocess.Popen(
                ["bash", "-e", "-o", "pipefail", "-x", "-c", ac],
                cwd=self._root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", start_new_session=True,
            )
        except OSError as e:
            return {"exitCode": None, "elapsed": 0.0, "timedOut": False, "output": f"AC 실행 불가: {e}"}

        timed_out = False
        try:
            output, _ = proc.communicate(timeout=self.AC_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group(proc)
            output, _ = proc.communicate()
        finally:
            self._kill_group(proc)

        return {
            "exitCode": proc.returncode,
            "elapsed": round(time.monotonic() - t0, 1),
            "timedOut": timed_out,
            "output": output,
        }

    @staticmethod
    def _kill_group(proc: subprocess.Popen):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def _gate(self, step_num: int) -> Optional[str]:
        """고정된 AC를 실행하고 결과를 stepN-output.json의 ac 키에 남긴다. 통과면 None, 실패면 재시도용 메시지."""
        with progress_indicator(f"Step {step_num}: AC 검증"):
            result = self._run_ac(self._acs[step_num])

        out_path = self._phase_dir / f"step{step_num}-output.json"
        try:
            output = self._read_json(out_path)
        except (OSError, ValueError):
            output = {"step": step_num}
        output["ac"] = result
        self._write_json(out_path, output)

        if result["exitCode"] == 0 and not result["timedOut"]:
            return None
        if result["timedOut"]:
            reason = "시간 초과"
        elif result["exitCode"] is None:
            reason = "실행 불가"
        else:
            reason = f"exit {result['exitCode']}"
        return f"AC 실패 ({reason})\n\n{result['output'][-3000:]}"

    # --- 헤더 & 검증 ---

    def _check_tools(self):
        missing = [t for t in ("claude", "git") if shutil.which(t) is None]
        if missing:
            print(f"  ERROR: 필요한 명령을 찾을 수 없습니다: {', '.join(missing)}")
            sys.exit(1)

    def _print_header(self):
        print(f"\n{'='*60}")
        print(f"  Harness Step Executor")
        print(f"  Phase: {self._phase_name} | Steps: {self._total}")
        if self._auto_push:
            print(f"  Auto-push: enabled")
        print(f"{'='*60}")

    def _check_blockers(self):
        index = self._read_json(self._index_file)
        for s in reversed(index["steps"]):
            if s["status"] == "error":
                print(f"\n  ✗ Step {s['step']} ({s['name']}) failed.")
                print(f"  Error: {s.get('error_message', 'unknown')}")
                print(f"  Fix and reset status to 'pending' to retry.")
                sys.exit(1)
            if s["status"] == "blocked":
                print(f"\n  ⏸ Step {s['step']} ({s['name']}) blocked.")
                print(f"  Reason: {s.get('blocked_reason', 'unknown')}")
                print(f"  Resolve and reset status to 'pending' to retry.")
                sys.exit(2)
            if s["status"] != "pending":
                break

    def _ensure_created_at(self):
        index = self._read_json(self._index_file)
        if "created_at" not in index:
            index["created_at"] = self._stamp()
            self._write_json(self._index_file, index)

    # --- 실행 루프 ---

    @staticmethod
    def _find_step(index: dict, step_num: int) -> dict:
        return next(s for s in index["steps"] if s["step"] == step_num)

    @staticmethod
    def _confirmed(step: dict) -> bool:
        """완료 확정 = completed이고 실행기가 기록한 completed_at이 있음. pending으로 되돌린 step의 옛 completed_at은 무효다."""
        return step.get("status") == "completed" and bool(step.get("completed_at"))

    def _sync_index(self, snapshot: dict, step_num: int) -> dict:
        """에이전트가 쓴 index에서 현재 step의 허용 필드만 snapshot에 옮겨 다시 쓴다.
        다른 step, completed_at 같은 실행기 필드, 깨진 JSON은 반영되지 않는다."""
        try:
            written = next((s for s in self._read_json(self._index_file)["steps"] if s["step"] == step_num), {})
        except (OSError, ValueError, KeyError, TypeError):
            written = {}
        target = self._find_step(snapshot, step_num)
        for key in self.AGENT_FIELDS:
            if key in written:
                target[key] = written[key]
        self._write_json(self._index_file, snapshot)
        return snapshot

    def _confirm_step(self, index: dict, step: dict):
        """AC 게이트를 통과한 step만 확정한다. completed_at은 실행기만 기록한다."""
        step["completed_at"] = self._stamp()
        self._write_json(self._index_file, index)
        self._commit_step(step["step"], step["name"])

    def _execute_single_step(self, step: dict, guardrails: str, prev_error: Optional[str] = None) -> bool:
        """단일 step 실행 (재시도 포함). AC 게이트를 통과하면 True, 마지막 실패나 차단이면 종료한다."""
        step_num, step_name = step["step"], step["name"]
        done = sum(1 for s in self._read_json(self._index_file)["steps"] if s["status"] == "completed")

        for attempt in range(1, self.MAX_RETRIES + 1):
            snapshot = self._read_json(self._index_file)
            step_context = self._build_step_context(snapshot)
            preamble = self._build_preamble(guardrails, step_context, prev_error)

            tag = f"Step {step_num}/{self._total - 1} ({done} done): {step_name}"
            if attempt > 1:
                tag += f" [retry {attempt}/{self.MAX_RETRIES}]"

            head = self._head()
            err_msg = None
            try:
                with progress_indicator(tag) as pi:
                    self._invoke_claude(step, preamble)
            except subprocess.TimeoutExpired as e:
                err_msg = f"Claude 호출 시간 초과 ({int(e.timeout)}초)"
            finally:
                index = self._sync_index(snapshot, step_num)
                self._undo_agent_commits(head)
            elapsed = int(pi.elapsed)
            s = self._find_step(index, step_num)

            if err_msg is None:
                if s["status"] == "completed":
                    err_msg = self._gate(step_num)
                    if err_msg is None:
                        self._confirm_step(index, s)
                        print(f"  ✓ Step {step_num}: {step_name} [{elapsed}s]")
                        return True
                elif s["status"] == "blocked":
                    s["blocked_at"] = self._stamp()
                    self._write_json(self._index_file, index)
                    print(f"  ⏸ Step {step_num}: {step_name} blocked [{elapsed}s]")
                    print(f"    Reason: {s.get('blocked_reason', '')}")
                    self._update_top_index("blocked")
                    sys.exit(2)
                else:
                    err_msg = str(s.get("error_message") or "Step did not update status")

            s.pop("summary", None)
            if attempt < self.MAX_RETRIES:
                s["status"] = "pending"
                s.pop("error_message", None)
                self._write_json(self._index_file, index)
                prev_error = err_msg
                print(f"  ↻ Step {step_num}: retry {attempt}/{self.MAX_RETRIES} — {err_msg.splitlines()[0]}")
            else:
                s["status"] = "error"
                s["error_message"] = f"[{self.MAX_RETRIES}회 시도 후 실패] {err_msg}"
                s["failed_at"] = self._stamp()
                self._write_json(self._index_file, index)
                print(f"  ✗ Step {step_num}: {step_name} failed after {self.MAX_RETRIES} attempts [{elapsed}s]")
                print(f"    Error: {err_msg}")
                print(f"    실패한 코드는 커밋하지 않고 working tree에 남겨 두었습니다.")
                self._update_top_index("error")
                sys.exit(1)

        return False  # unreachable

    def _execute_all_steps(self, guardrails: str):
        while True:
            index = self._read_json(self._index_file)
            step = next(
                (s for s in index["steps"]
                 if s["status"] == "pending" or (s["status"] == "completed" and not s.get("completed_at"))),
                None,
            )
            if step is None:
                print("\n  All steps completed!")
                return

            prev_error = None
            if step["status"] == "completed":
                # 완료 보고 뒤 확정 전에 중단된 step: 에이전트 없이 게이트만 다시 돌린다
                prev_error = self._gate(step["step"])
                if prev_error is None:
                    self._confirm_step(index, step)
                    print(f"  ✓ Step {step['step']}: {step['name']} (재개 후 AC 통과)")
                    continue
                step["status"] = "pending"
                step.pop("summary", None)
                print(f"  ↻ Step {step['step']}: 재개 후 AC 실패 — 에이전트로 이어 갑니다")

            step.setdefault("started_at", self._stamp())
            self._write_json(self._index_file, index)
            self._execute_single_step(step, guardrails, prev_error)

    def _finalize(self):
        index = self._read_json(self._index_file)
        unconfirmed = [f"Step {s['step']} ({s.get('status')})" for s in index["steps"] if not self._confirmed(s)]
        if unconfirmed:
            print(f"\n  ERROR: 확정되지 않은 step이 있어 phase를 완료로 기록하지 않습니다: {', '.join(unconfirmed)}")
            sys.exit(1)

        index["completed_at"] = self._stamp()
        self._write_json(self._index_file, index)
        self._update_top_index("completed")

        self._run_git("add", "-A")
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = f"chore({self._phase_name}): mark phase completed"
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  ✓ {msg}")

        if self._auto_push:
            branch = f"feat-{self._phase_name}"
            r = self._run_git("push", "-u", "origin", branch)
            if r.returncode != 0:
                print(f"\n  ERROR: git push 실패: {r.stderr.strip()}")
                sys.exit(1)
            print(f"  ✓ Pushed to origin/{branch}")

        print(f"\n{'='*60}")
        print(f"  Phase '{self._phase_name}' completed!")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Harness Step Executor")
    parser.add_argument("phase_dir", help="Phase directory name (e.g. 0-mvp)")
    parser.add_argument("--push", action="store_true", help="Push branch after completion")
    args = parser.parse_args()

    StepExecutor(args.phase_dir, auto_push=args.push).run()


if __name__ == "__main__":
    main()
