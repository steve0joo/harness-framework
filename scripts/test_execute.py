"""
execute.py 리팩터링 안전망 테스트.
리팩터링 전후 동작이 동일한지 검증한다.
"""

import json
import os
import shlex
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import execute as ex


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_project(tmp_path):
    """phases/, CLAUDE.md, docs/ 를 갖춘 임시 프로젝트 구조."""
    phases_dir = tmp_path / "phases"
    phases_dir.mkdir()

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Rules\n- rule one\n- rule two")

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "arch.md").write_text("# Architecture\nSome content")
    (docs_dir / "guide.md").write_text("# Guide\nAnother doc")

    return tmp_path


@pytest.fixture
def phase_dir(tmp_project):
    """step 3개를 가진 phase 디렉토리."""
    d = tmp_project / "phases" / "0-mvp"
    d.mkdir()

    index = {
        "project": "TestProject",
        "phase": "mvp",
        "steps": [
            {"step": 0, "name": "setup", "status": "completed", "summary": "프로젝트 초기화 완료"},
            {"step": 1, "name": "core", "status": "completed", "summary": "핵심 로직 구현"},
            {"step": 2, "name": "ui", "status": "pending"},
        ],
    }
    (d / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False))
    (d / "step2.md").write_text("# Step 2: UI\n\nUI를 구현하세요.")

    return d


@pytest.fixture
def top_index(tmp_project):
    """phases/index.json (top-level)."""
    top = {
        "phases": [
            {"dir": "0-mvp", "status": "pending"},
            {"dir": "1-polish", "status": "pending"},
        ]
    }
    p = tmp_project / "phases" / "index.json"
    p.write_text(json.dumps(top, indent=2))
    return p


@pytest.fixture
def executor(tmp_project, phase_dir):
    """테스트용 StepExecutor 인스턴스. git 호출은 별도 mock 필요."""
    with patch.object(ex, "ROOT", tmp_project):
        inst = ex.StepExecutor("0-mvp")
    # 내부 경로를 tmp_project 기준으로 재설정
    inst._root = str(tmp_project)
    inst._phases_dir = tmp_project / "phases"
    inst._phase_dir = phase_dir
    inst._phase_dir_name = "0-mvp"
    inst._index_file = phase_dir / "index.json"
    inst._top_index_file = tmp_project / "phases" / "index.json"
    return inst


# ---------------------------------------------------------------------------
# _stamp (= 이전 now_iso)
# ---------------------------------------------------------------------------

class TestStamp:
    def test_returns_kst_timestamp(self, executor):
        result = executor._stamp()
        assert "+0900" in result

    def test_format_is_iso(self, executor):
        result = executor._stamp()
        dt = datetime.strptime(result, "%Y-%m-%dT%H:%M:%S%z")
        assert dt.tzinfo is not None

    def test_is_current_time(self, executor):
        before = datetime.now(ex.StepExecutor.TZ).replace(microsecond=0)
        result = executor._stamp()
        after = datetime.now(ex.StepExecutor.TZ).replace(microsecond=0) + timedelta(seconds=1)
        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%S%z")
        assert before <= parsed <= after


# ---------------------------------------------------------------------------
# _read_json / _write_json
# ---------------------------------------------------------------------------

class TestJsonHelpers:
    def test_roundtrip(self, tmp_path):
        data = {"key": "값", "nested": [1, 2, 3]}
        p = tmp_path / "test.json"
        ex.StepExecutor._write_json(p, data)
        loaded = ex.StepExecutor._read_json(p)
        assert loaded == data

    def test_save_ensures_ascii_false(self, tmp_path):
        p = tmp_path / "test.json"
        ex.StepExecutor._write_json(p, {"한글": "테스트"})
        raw = p.read_text()
        assert "한글" in raw
        assert "\\u" not in raw

    def test_save_indented(self, tmp_path):
        p = tmp_path / "test.json"
        ex.StepExecutor._write_json(p, {"a": 1})
        raw = p.read_text()
        assert "\n" in raw

    def test_load_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ex.StepExecutor._read_json(tmp_path / "nope.json")


# ---------------------------------------------------------------------------
# _load_guardrails
# ---------------------------------------------------------------------------

class TestLoadGuardrails:
    def test_loads_claude_md_and_docs(self, executor, tmp_project):
        with patch.object(ex, "ROOT", tmp_project):
            result = executor._load_guardrails()
        assert "# Rules" in result
        assert "rule one" in result
        assert "# Architecture" in result
        assert "# Guide" in result

    def test_sections_separated_by_divider(self, executor, tmp_project):
        with patch.object(ex, "ROOT", tmp_project):
            result = executor._load_guardrails()
        assert "---" in result

    def test_docs_sorted_alphabetically(self, executor, tmp_project):
        with patch.object(ex, "ROOT", tmp_project):
            result = executor._load_guardrails()
        arch_pos = result.index("arch")
        guide_pos = result.index("guide")
        assert arch_pos < guide_pos

    def test_no_claude_md(self, executor, tmp_project):
        (tmp_project / "CLAUDE.md").unlink()
        with patch.object(ex, "ROOT", tmp_project):
            result = executor._load_guardrails()
        assert "CLAUDE.md" not in result
        assert "Architecture" in result

    def test_no_docs_dir(self, executor, tmp_project):
        import shutil
        shutil.rmtree(tmp_project / "docs")
        with patch.object(ex, "ROOT", tmp_project):
            result = executor._load_guardrails()
        assert "Rules" in result
        assert "Architecture" not in result

    def test_empty_project(self, tmp_path):
        with patch.object(ex, "ROOT", tmp_path):
            # executor가 필요 없는 static-like 동작이므로 임시 인스턴스
            phases_dir = tmp_path / "phases" / "dummy"
            phases_dir.mkdir(parents=True)
            idx = {"project": "T", "phase": "t", "steps": []}
            (phases_dir / "index.json").write_text(json.dumps(idx))
            inst = ex.StepExecutor.__new__(ex.StepExecutor)
            result = inst._load_guardrails()
        assert result == ""


# ---------------------------------------------------------------------------
# _build_step_context
# ---------------------------------------------------------------------------

class TestBuildStepContext:
    def test_includes_completed_with_summary(self, phase_dir):
        index = json.loads((phase_dir / "index.json").read_text())
        result = ex.StepExecutor._build_step_context(index)
        assert "Step 0 (setup): 프로젝트 초기화 완료" in result
        assert "Step 1 (core): 핵심 로직 구현" in result

    def test_excludes_pending(self, phase_dir):
        index = json.loads((phase_dir / "index.json").read_text())
        result = ex.StepExecutor._build_step_context(index)
        assert "ui" not in result

    def test_excludes_completed_without_summary(self, phase_dir):
        index = json.loads((phase_dir / "index.json").read_text())
        del index["steps"][0]["summary"]
        result = ex.StepExecutor._build_step_context(index)
        assert "setup" not in result
        assert "core" in result

    def test_empty_when_no_completed(self):
        index = {"steps": [{"step": 0, "name": "a", "status": "pending"}]}
        result = ex.StepExecutor._build_step_context(index)
        assert result == ""

    def test_has_header(self, phase_dir):
        index = json.loads((phase_dir / "index.json").read_text())
        result = ex.StepExecutor._build_step_context(index)
        assert result.startswith("## 이전 Step 산출물")


# ---------------------------------------------------------------------------
# _build_preamble
# ---------------------------------------------------------------------------

class TestBuildPreamble:
    def test_includes_project_name(self, executor):
        result = executor._build_preamble("", "")
        assert "TestProject" in result

    def test_includes_guardrails(self, executor):
        result = executor._build_preamble("GUARD_CONTENT", "")
        assert "GUARD_CONTENT" in result

    def test_includes_step_context(self, executor):
        ctx = "## 이전 Step 산출물\n\n- Step 0: done"
        result = executor._build_preamble("", ctx)
        assert "이전 Step 산출물" in result

    def test_forbids_commit(self, executor):
        result = executor._build_preamble("", "")
        assert "커밋하지 마라" in result
        assert "feat(mvp):" not in result

    def test_forbids_editing_protected_files_and_other_steps(self, executor):
        result = executor._build_preamble("", "")
        assert "하네스 파일(.claude/, scripts/execute.py), docs/, CLAUDE.md, step 파일을 수정하지 마라" in result
        assert "실행기가 이 시도를 실패로 처리한다" in result
        assert "다른 step의 상태" in result

    def test_says_executor_reverifies(self, executor):
        result = executor._build_preamble("", "")
        assert "실행기가 AC로 다시 검증한다" in result

    def test_asks_for_general_logic_not_test_fitting(self, executor):
        result = executor._build_preamble("", "")
        assert "테스트는 동작을 검증하는 수단이다" in result
        assert "일반적인 로직을 구현하라" in result

    def test_includes_rules(self, executor):
        result = executor._build_preamble("", "")
        assert "작업 규칙" in result
        assert "AC" in result

    def test_no_retry_section_by_default(self, executor):
        result = executor._build_preamble("", "")
        assert "이전 시도 실패" not in result

    def test_retry_section_with_prev_error(self, executor):
        result = executor._build_preamble("", "", prev_error="타입 에러 발생")
        assert "이전 시도 실패" in result
        assert "타입 에러 발생" in result

    def test_retry_budget_not_delegated_to_agent(self, executor):
        result = executor._build_preamble("", "")
        assert "회 수정 시도" not in result

    def test_includes_index_path(self, executor):
        result = executor._build_preamble("", "")
        assert "/phases/0-mvp/index.json" in result


# ---------------------------------------------------------------------------
# _update_top_index
# ---------------------------------------------------------------------------

class TestUpdateTopIndex:
    def test_completed(self, executor, top_index):
        executor._top_index_file = top_index
        executor._update_top_index("completed")
        data = json.loads(top_index.read_text())
        mvp = next(p for p in data["phases"] if p["dir"] == "0-mvp")
        assert mvp["status"] == "completed"
        assert "completed_at" in mvp

    def test_error(self, executor, top_index):
        executor._top_index_file = top_index
        executor._update_top_index("error")
        data = json.loads(top_index.read_text())
        mvp = next(p for p in data["phases"] if p["dir"] == "0-mvp")
        assert mvp["status"] == "error"
        assert "failed_at" in mvp

    def test_blocked(self, executor, top_index):
        executor._top_index_file = top_index
        executor._update_top_index("blocked")
        data = json.loads(top_index.read_text())
        mvp = next(p for p in data["phases"] if p["dir"] == "0-mvp")
        assert mvp["status"] == "blocked"
        assert "blocked_at" in mvp

    def test_other_phases_unchanged(self, executor, top_index):
        executor._top_index_file = top_index
        executor._update_top_index("completed")
        data = json.loads(top_index.read_text())
        polish = next(p for p in data["phases"] if p["dir"] == "1-polish")
        assert polish["status"] == "pending"

    def test_nonexistent_dir_is_noop(self, executor, top_index):
        executor._top_index_file = top_index
        executor._phase_dir_name = "no-such-dir"
        original = json.loads(top_index.read_text())
        executor._update_top_index("completed")
        after = json.loads(top_index.read_text())
        for p_before, p_after in zip(original["phases"], after["phases"]):
            assert p_before["status"] == p_after["status"]

    def test_no_top_index_file(self, executor, tmp_path):
        executor._top_index_file = tmp_path / "nonexistent.json"
        executor._update_top_index("completed")  # should not raise


# ---------------------------------------------------------------------------
# _checkout_branch (mocked)
# ---------------------------------------------------------------------------

class TestCheckoutBranch:
    def _mock_git(self, executor, responses):
        call_idx = {"i": 0}
        def fake_git(*args):
            idx = call_idx["i"]
            call_idx["i"] += 1
            if idx < len(responses):
                return responses[idx]
            return MagicMock(returncode=0, stdout="", stderr="")
        executor._run_git = fake_git

    def test_already_on_branch(self, executor):
        self._mock_git(executor, [
            MagicMock(returncode=0, stdout="feat-mvp\n", stderr=""),
        ])
        executor._checkout_branch()  # should return without checkout

    def test_branch_exists_checkout(self, executor):
        self._mock_git(executor, [
            MagicMock(returncode=0, stdout="main\n", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ])
        executor._checkout_branch()

    def test_branch_not_exists_create(self, executor):
        self._mock_git(executor, [
            MagicMock(returncode=0, stdout="main\n", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="not found"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ])
        executor._checkout_branch()

    def test_checkout_fails_exits(self, executor):
        self._mock_git(executor, [
            MagicMock(returncode=0, stdout="main\n", stderr=""),
            MagicMock(returncode=1, stdout="", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="dirty tree"),
        ])
        with pytest.raises(SystemExit) as exc_info:
            executor._checkout_branch()
        assert exc_info.value.code == 1

    def test_no_git_exits(self, executor):
        self._mock_git(executor, [
            MagicMock(returncode=1, stdout="", stderr="not a git repo"),
        ])
        with pytest.raises(SystemExit) as exc_info:
            executor._checkout_branch()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _commit_step (mocked)
# ---------------------------------------------------------------------------

class TestCommitStep:
    def test_two_phase_commit(self, executor):
        calls = []
        def fake_git(*args):
            calls.append(args)
            if args[:2] == ("diff", "--cached"):
                return MagicMock(returncode=1)
            return MagicMock(returncode=0, stdout="", stderr="")
        executor._run_git = fake_git

        executor._commit_step(2, "ui")

        commit_calls = [c for c in calls if c[0] == "commit"]
        assert len(commit_calls) == 2
        assert "feat(mvp):" in commit_calls[0][2]
        assert "chore(mvp):" in commit_calls[1][2]

    def test_no_code_changes_skips_feat_commit(self, executor):
        call_count = {"diff": 0}
        calls = []
        def fake_git(*args):
            calls.append(args)
            if args[:2] == ("diff", "--cached"):
                call_count["diff"] += 1
                if call_count["diff"] == 1:
                    return MagicMock(returncode=0)
                return MagicMock(returncode=1)
            return MagicMock(returncode=0, stdout="", stderr="")
        executor._run_git = fake_git

        executor._commit_step(2, "ui")

        commit_msgs = [c[2] for c in calls if c[0] == "commit"]
        assert len(commit_msgs) == 1
        assert "chore" in commit_msgs[0]


# ---------------------------------------------------------------------------
# _invoke_claude (mocked)
# ---------------------------------------------------------------------------

class TestInvokeClaude:
    def test_invokes_claude_with_correct_args(self, executor):
        mock_result = MagicMock(returncode=0, stdout='{"result": "ok"}', stderr="")
        step = {"step": 2, "name": "ui"}
        preamble = "PREAMBLE\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            output = executor._invoke_claude(step, preamble)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--dangerously-skip-permissions" in cmd
        assert "--output-format" in cmd
        assert "PREAMBLE" in cmd[-1]
        assert "UI를 구현하세요" in cmd[-1]

    def test_saves_output_json(self, executor):
        mock_result = MagicMock(returncode=0, stdout='{"ok": true}', stderr="")
        step = {"step": 2, "name": "ui"}

        with patch("subprocess.run", return_value=mock_result):
            executor._invoke_claude(step, "preamble")

        output_file = executor._phase_dir / "step2-output.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["step"] == 2
        assert data["name"] == "ui"
        assert data["exitCode"] == 0

    def test_nonexistent_step_file_exits(self, executor):
        step = {"step": 99, "name": "nonexistent"}
        with pytest.raises(SystemExit) as exc_info:
            executor._invoke_claude(step, "preamble")
        assert exc_info.value.code == 1

    def test_timeout_is_1800(self, executor):
        mock_result = MagicMock(returncode=0, stdout="{}", stderr="")
        step = {"step": 2, "name": "ui"}

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            executor._invoke_claude(step, "preamble")

        assert mock_run.call_args[1]["timeout"] == 1800


# ---------------------------------------------------------------------------
# progress_indicator (= 이전 Spinner)
# ---------------------------------------------------------------------------

class TestProgressIndicator:
    def test_context_manager(self):
        import time
        with ex.progress_indicator("test") as pi:
            time.sleep(0.15)
        assert pi.elapsed >= 0.1

    def test_elapsed_increases(self):
        import time
        with ex.progress_indicator("test") as pi:
            time.sleep(0.2)
        assert pi.elapsed > 0


# ---------------------------------------------------------------------------
# main() CLI 파싱 (mocked)
# ---------------------------------------------------------------------------

class TestMainCli:
    def test_no_args_exits(self):
        with patch("sys.argv", ["execute.py"]):
            with pytest.raises(SystemExit) as exc_info:
                ex.main()
            assert exc_info.value.code == 2  # argparse exits with 2

    def test_invalid_phase_dir_exits(self):
        with patch("sys.argv", ["execute.py", "nonexistent"]):
            with patch.object(ex, "ROOT", Path("/tmp/fake_nonexistent")):
                with pytest.raises(SystemExit) as exc_info:
                    ex.main()
                assert exc_info.value.code == 1

    def test_missing_index_exits(self, tmp_project):
        (tmp_project / "phases" / "empty").mkdir()
        with patch("sys.argv", ["execute.py", "empty"]):
            with patch.object(ex, "ROOT", tmp_project):
                with pytest.raises(SystemExit) as exc_info:
                    ex.main()
                assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _check_blockers (= 이전 main() error/blocked 체크)
# ---------------------------------------------------------------------------

class TestCheckBlockers:
    def _make_executor_with_steps(self, tmp_project, steps):
        d = tmp_project / "phases" / "test-phase"
        d.mkdir(exist_ok=True)
        index = {"project": "T", "phase": "test", "steps": steps}
        (d / "index.json").write_text(json.dumps(index))

        with patch.object(ex, "ROOT", tmp_project):
            inst = ex.StepExecutor.__new__(ex.StepExecutor)
        inst._root = str(tmp_project)
        inst._phases_dir = tmp_project / "phases"
        inst._phase_dir = d
        inst._phase_dir_name = "test-phase"
        inst._index_file = d / "index.json"
        inst._top_index_file = tmp_project / "phases" / "index.json"
        inst._phase_name = "test"
        inst._total = len(steps)
        return inst

    def test_error_step_exits_1(self, tmp_project):
        steps = [
            {"step": 0, "name": "ok", "status": "completed"},
            {"step": 1, "name": "bad", "status": "error", "error_message": "fail"},
        ]
        inst = self._make_executor_with_steps(tmp_project, steps)
        with pytest.raises(SystemExit) as exc_info:
            inst._check_blockers()
        assert exc_info.value.code == 1

    def test_blocked_step_exits_2(self, tmp_project):
        steps = [
            {"step": 0, "name": "ok", "status": "completed"},
            {"step": 1, "name": "stuck", "status": "blocked", "blocked_reason": "API key"},
        ]
        inst = self._make_executor_with_steps(tmp_project, steps)
        with pytest.raises(SystemExit) as exc_info:
            inst._check_blockers()
        assert exc_info.value.code == 2


# ===========================================================================
# R2: AC 계약 · 게이트 · 강제 장치 · 흐름 · 재개
# 흐름 테스트는 임시 git 저장소와 실제 bash 게이트를 쓰고, claude만 가짜로 바꾼다.
# ===========================================================================

def ac_step(num, name, ac):
    """AC 블록 하나를 가진 step 파일 내용."""
    return (
        f"# Step {num}: {name}\n\n## 작업\n\n{name} 작업\n\n"
        f"## Acceptance Criteria\n\n```bash\n{ac}\n```\n\n"
        f"## 검증 절차\n\n1. AC를 실행한다.\n"
    )


def extract(md):
    return ex.StepExecutor._extract_ac(md)


def git(root, *args):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def log(root):
    return git(root, "log", "--format=%s").splitlines()


def read_index(root):
    return json.loads((root / "phases" / "0-mvp" / "index.json").read_text())


def report(root, num, status, **fields):
    """에이전트처럼 index.json의 step 항목을 고친다."""
    p = root / "phases" / "0-mvp" / "index.json"
    idx = json.loads(p.read_text())
    s = next(s for s in idx["steps"] if s["step"] == num)
    s.update(status=status, **fields)
    p.write_text(json.dumps(idx, indent=2))


def work(root, filename, content):
    """파일을 쓰고 completed를 보고하는 에이전트 동작."""
    def act(step):
        (root / filename).write_text(content)
        report(root, step["step"], "completed", summary=f"{filename} 작성")
    return act


def fake_agent(runner, *actions):
    """호출마다 actions를 차례로 실행하는 가짜 claude. (step 번호, preamble) 기록을 돌려준다."""
    calls = []

    def invoke(step, preamble):
        calls.append((step["step"], preamble))
        actions[len(calls) - 1](step)

    runner._invoke_claude = invoke
    return calls


def run_phase(runner, root):
    with patch.object(ex, "ROOT", root), patch.object(ex.shutil, "which", return_value="/usr/bin/true"):
        runner.run()


def wait_dead(pid, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def repo(tmp_path):
    """git 저장소 안에 step 2개짜리 phase를 둔 프로젝트. AC는 a.txt, b.txt에 ok가 있는지 확인한다."""
    root = tmp_path / "proj"
    d = root / "phases" / "0-mvp"
    d.mkdir(parents=True)
    (root / "CLAUDE.md").write_text("# Rules")
    index = {
        "project": "T",
        "phase": "mvp",
        "steps": [
            {"step": 0, "name": "first", "status": "pending"},
            {"step": 1, "name": "second", "status": "pending"},
        ],
    }
    (d / "index.json").write_text(json.dumps(index, indent=2))
    (d / "step0.md").write_text(ac_step(0, "first", "grep -q ok a.txt"))
    (d / "step1.md").write_text(ac_step(1, "second", "grep -q ok b.txt"))
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "test")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


@pytest.fixture
def runner(repo):
    with patch.object(ex, "ROOT", repo):
        return ex.StepExecutor("0-mvp")


# ---------------------------------------------------------------------------
# AC 추출
# ---------------------------------------------------------------------------

class TestExtractAc:
    def test_returns_block(self):
        ac = "python3 -m pytest tests/test_a.py -q\nnpm test"
        assert extract(ac_step(0, "a", ac)) == ac

    def test_missing_header(self):
        with pytest.raises(ValueError, match="Acceptance Criteria"):
            extract("# Step 0\n\n```bash\nnpm test\n```\n")

    def test_no_block(self):
        with pytest.raises(ValueError, match="0개"):
            extract("## Acceptance Criteria\n\nnpm test 통과\n")

    def test_two_blocks(self):
        md = "## Acceptance Criteria\n\n```bash\nnpm test\n```\n\n```bash\nnpm run build\n```\n"
        with pytest.raises(ValueError, match="2개"):
            extract(md)

    def test_empty_block(self):
        with pytest.raises(ValueError, match="비어"):
            extract("## Acceptance Criteria\n\n```bash\n\n```\n")

    def test_comment_only_block_is_empty(self):
        with pytest.raises(ValueError, match="비어"):
            extract(ac_step(0, "a", "# 나중에 채움"))

    def test_unclosed_fence(self):
        with pytest.raises(ValueError, match="닫히지"):
            extract("## Acceptance Criteria\n\n```bash\nnpm test\n\n## 검증 절차\n")

    def test_dangerous_command(self):
        with pytest.raises(ValueError, match="rm -rf"):
            extract(ac_step(0, "a", "npm test\nrm -rf dist"))

    def test_block_in_next_section_not_counted(self):
        md = ac_step(0, "a", "npm test") + "\n```bash\nnpm run e2e\n```\n"
        assert extract(md) == "npm test"

    def test_bash_comment_inside_block_does_not_end_section(self):
        ac = "## 핵심 동작\npython3 -m pytest tests/test_a.py -q"
        assert extract(ac_step(0, "a", ac)) == ac


class TestLoadAcs:
    def test_freezes_unconfirmed_steps(self, runner):
        runner._load_acs()
        assert runner._acs == {0: "grep -q ok a.txt", 1: "grep -q ok b.txt"}

    def test_reports_all_errors_at_once(self, runner, repo, capsys):
        d = repo / "phases" / "0-mvp"
        (d / "step0.md").write_text("# Step 0\n\nAC 없음\n")
        (d / "step1.md").write_text(ac_step(1, "second", "git reset --hard HEAD"))
        with pytest.raises(SystemExit) as e:
            runner._load_acs()
        assert e.value.code == 1
        out = capsys.readouterr().out
        assert "Step 0" in out and "Step 1" in out

    def test_missing_step_file(self, runner, repo, capsys):
        (repo / "phases" / "0-mvp" / "step1.md").unlink()
        with pytest.raises(SystemExit):
            runner._load_acs()
        assert "step1.md" in capsys.readouterr().out

    def test_skips_confirmed_steps(self, runner, repo):
        report(repo, 0, "completed", completed_at="2026-01-01T00:00:00+0900")
        (repo / "phases" / "0-mvp" / "step0.md").write_text("# Step 0\n\n옛 형식, AC 없음\n")
        runner._load_acs()
        assert runner._acs == {1: "grep -q ok b.txt"}


# ---------------------------------------------------------------------------
# AC 게이트
# ---------------------------------------------------------------------------

class TestRunAc:
    def test_pass_runs_in_root_with_trace(self, runner, repo):
        r = runner._run_ac("echo hello\npwd -P")
        assert r["exitCode"] == 0 and r["timedOut"] is False
        assert "+ echo hello" in r["output"]
        assert os.path.realpath(repo) in r["output"]
        assert r["elapsed"] >= 0

    def test_middle_command_failure(self, runner):
        r = runner._run_ac("false\necho after")
        assert r["exitCode"] == 1
        assert "after" not in r["output"]

    def test_pipe_head_failure(self, runner):
        r = runner._run_ac("false | cat")
        assert r["exitCode"] != 0

    def test_timeout_kills_process_group(self, runner, tmp_path):
        runner.AC_TIMEOUT = 1
        pidfile = tmp_path / "pid"
        r = runner._run_ac(f"sleep 30 &\necho $! > {shlex.quote(str(pidfile))}\nwait")
        assert r["timedOut"] is True
        assert r["elapsed"] < 10
        assert wait_dead(int(pidfile.read_text()))

    def test_interrupt_kills_process_group(self, runner, tmp_path):
        pidfile = tmp_path / "pid"

        class InterruptedPopen(subprocess.Popen):
            def communicate(self, *args, **kwargs):
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and not (pidfile.exists() and pidfile.read_text().strip()):
                    time.sleep(0.01)
                raise KeyboardInterrupt

        with patch.object(ex.subprocess, "Popen", InterruptedPopen):
            with pytest.raises(KeyboardInterrupt):
                runner._run_ac(f"sleep 30 &\necho $! > {shlex.quote(str(pidfile))}\nwait")
        assert wait_dead(int(pidfile.read_text()))

    def test_cannot_run(self, runner):
        with patch.object(ex.subprocess, "Popen", side_effect=FileNotFoundError("bash")):
            r = runner._run_ac("true")
        assert r["exitCode"] is None
        assert "bash" in r["output"]


class TestCheckTools:
    @pytest.mark.parametrize("missing", ["claude", "git"])
    def test_missing_tool_exits(self, runner, missing, capsys):
        with patch.object(ex.shutil, "which", side_effect=lambda t: None if t == missing else f"/usr/bin/{t}"):
            with pytest.raises(SystemExit) as e:
                runner._check_tools()
        assert e.value.code == 1
        assert missing in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 강제 장치
# ---------------------------------------------------------------------------

class TestEnforcement:
    @staticmethod
    def run_step0(runner, repo):
        runner._load_acs()
        runner._freeze_protected()
        runner._execute_single_step(read_index(repo)["steps"][0], "")

    def test_agent_cannot_confirm_or_touch_other_steps(self, runner, repo):
        def forge(step):
            (repo / "a.txt").write_text("bad")
            report(repo, 0, "completed", summary="x", completed_at="forged")
            report(repo, 1, "completed", summary="y", completed_at="forged")

        runner.MAX_RETRIES = 1
        fake_agent(runner, forge)
        with pytest.raises(SystemExit):
            self.run_step0(runner, repo)
        s0, s1 = read_index(repo)["steps"]
        assert s0["status"] == "error" and "completed_at" not in s0
        assert s1 == {"step": 1, "name": "second", "status": "pending"}

    def test_broken_json_means_no_change(self, runner, repo):
        def corrupt(step):
            (repo / "phases" / "0-mvp" / "index.json").write_text("{broken")

        calls = fake_agent(runner, corrupt, work(repo, "a.txt", "ok"))
        self.run_step0(runner, repo)
        assert "Step did not update status" in calls[1][1]
        assert read_index(repo)["steps"][0]["completed_at"]

    def test_agent_commit_is_soft_reset(self, runner, repo, capsys):
        def commit(step):
            work(repo, "a.txt", "ok")(step)
            git(repo, "add", "a.txt")
            git(repo, "commit", "-qm", "agent commit")

        fake_agent(runner, commit)
        self.run_step0(runner, repo)
        assert log(repo) == ["chore(mvp): step 0 output", "feat(mvp): step 0 — first", "init"]
        assert "a.txt" in git(repo, "show", "--name-only", "--format=", "HEAD~1")
        assert "reset --soft" in capsys.readouterr().out

    def test_protected_file_change_fails_attempt(self, runner, repo):
        hook = repo / ".claude" / "hooks" / "tdd_guard.py"

        def tamper(step):
            hook.parent.mkdir(parents=True)
            hook.write_text("")
            (repo / "CLAUDE.md").write_text("# 바뀐 규칙")
            work(repo, "a.txt", "ok")(step)

        def restore(step):
            hook.unlink()
            (repo / "CLAUDE.md").write_text("# Rules")
            work(repo, "a.txt", "ok")(step)

        calls = fake_agent(runner, tamper, restore)
        self.run_step0(runner, repo)
        assert "보호 파일 변경: .claude/hooks/tdd_guard.py, CLAUDE.md" in calls[1][1]
        assert read_index(repo)["steps"][0]["completed_at"]

    def test_protected_baseline_is_run_start_not_head(self, runner, repo):
        (repo / "CLAUDE.md").write_text("# 사용자가 실행 전에 고친 규칙")
        fake_agent(runner, work(repo, "a.txt", "ok"))
        self.run_step0(runner, repo)
        assert read_index(repo)["steps"][0]["completed_at"]

    def test_pycache_in_protected_dir_is_ignored(self, runner, repo):
        def compile_hooks(step):
            cache = repo / ".claude" / "hooks" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "bash_guard.cpython-312.pyc").write_bytes(b"x")
            work(repo, "a.txt", "ok")(step)

        fake_agent(runner, compile_hooks)
        self.run_step0(runner, repo)
        assert read_index(repo)["steps"][0]["completed_at"]

    def test_changed_ac_is_judged_by_frozen_copy(self, runner, repo):
        def cheat(step):
            (repo / "phases" / "0-mvp" / "step0.md").write_text(ac_step(0, "first", "true"))
            report(repo, 0, "completed", summary="x")

        runner.MAX_RETRIES = 1
        fake_agent(runner, cheat)
        with pytest.raises(SystemExit):
            self.run_step0(runner, repo)
        assert read_index(repo)["steps"][0]["status"] == "error"


# ---------------------------------------------------------------------------
# 시도 흐름
# ---------------------------------------------------------------------------

class TestFlow:
    def test_completes_all_steps(self, runner, repo):
        calls = fake_agent(runner, work(repo, "a.txt", "ok"), work(repo, "b.txt", "ok"))
        run_phase(runner, repo)
        idx = read_index(repo)
        assert [c[0] for c in calls] == [0, 1]
        assert all(s.get("completed_at") for s in idx["steps"])
        assert "completed_at" in idx
        assert log(repo) == [
            "chore(mvp): mark phase completed",
            "chore(mvp): step 1 output",
            "feat(mvp): step 1 — second",
            "chore(mvp): step 0 output",
            "feat(mvp): step 0 — first",
            "init",
        ]
        out = json.loads((repo / "phases" / "0-mvp" / "step0-output.json").read_text())
        assert out["ac"]["exitCode"] == 0

    def test_gate_failure_is_retried_with_ac_output(self, runner, repo):
        calls = fake_agent(
            runner, work(repo, "a.txt", "bad"), work(repo, "a.txt", "ok"), work(repo, "b.txt", "ok")
        )
        run_phase(runner, repo)
        assert [c[0] for c in calls] == [0, 0, 1]
        assert "AC 실패 (exit 1)" in calls[1][1]
        assert "+ grep -q ok a.txt" in calls[1][1]
        assert "completed_at" in read_index(repo)

    def test_last_failure_leaves_no_commit(self, runner, repo):
        fake_agent(runner, *[work(repo, "a.txt", "bad")] * 3)
        with pytest.raises(SystemExit) as e:
            run_phase(runner, repo)
        assert e.value.code == 1
        s0 = read_index(repo)["steps"][0]
        assert s0["status"] == "error"
        assert "failed_at" in s0 and "completed_at" not in s0
        assert "AC 실패" in s0["error_message"]
        assert log(repo) == ["init"]
        assert (repo / "a.txt").read_text() == "bad"

    def test_blocked_exits_2(self, runner, repo):
        fake_agent(runner, lambda step: report(repo, 0, "blocked", blocked_reason="API 키 필요"))
        with pytest.raises(SystemExit) as e:
            run_phase(runner, repo)
        assert e.value.code == 2
        s0 = read_index(repo)["steps"][0]
        assert s0["status"] == "blocked" and "blocked_at" in s0

    def test_claude_timeout_counts_as_attempt(self, runner, repo):
        def hang(step):
            raise subprocess.TimeoutExpired("claude", 1800)

        calls = fake_agent(runner, hang, work(repo, "a.txt", "ok"), work(repo, "b.txt", "ok"))
        run_phase(runner, repo)
        assert [c[0] for c in calls] == [0, 0, 1]
        assert "호출 시간 초과" in calls[1][1]


# ---------------------------------------------------------------------------
# 재개와 마무리
# ---------------------------------------------------------------------------

class TestResume:
    def test_reported_step_is_confirmed_by_gate_only(self, runner, repo):
        report(repo, 0, "completed", summary="a.txt 작성")
        (repo / "a.txt").write_text("ok")
        calls = fake_agent(runner, work(repo, "b.txt", "ok"))
        run_phase(runner, repo)
        assert [c[0] for c in calls] == [1]
        assert read_index(repo)["steps"][0]["completed_at"]
        assert "feat(mvp): step 0 — first" in log(repo)

    def test_failed_regate_continues_with_agent(self, runner, repo):
        report(repo, 0, "completed", summary="a.txt 작성")
        (repo / "a.txt").write_text("bad")
        calls = fake_agent(runner, work(repo, "a.txt", "ok"), work(repo, "b.txt", "ok"))
        run_phase(runner, repo)
        assert [c[0] for c in calls] == [0, 1]
        assert "AC 실패 (exit 1)" in calls[0][1]

    def test_interrupt_during_gate_then_resume(self, runner, repo):
        fake_agent(runner, work(repo, "a.txt", "ok"))
        with patch.object(runner, "_run_ac", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                run_phase(runner, repo)
        s0 = read_index(repo)["steps"][0]
        assert s0["status"] == "completed" and "completed_at" not in s0

        with patch.object(ex, "ROOT", repo):
            again = ex.StepExecutor("0-mvp")
        calls = fake_agent(again, work(repo, "b.txt", "ok"))
        run_phase(again, repo)
        assert [c[0] for c in calls] == [1]
        assert read_index(repo)["steps"][0]["completed_at"]

    def test_legacy_completed_at_is_accepted(self, runner, repo):
        report(repo, 0, "completed", summary="old", completed_at="2026-01-01T00:00:00+0900")
        (repo / "phases" / "0-mvp" / "step0.md").write_text("# Step 0\n\n옛 형식, AC 없음\n")
        calls = fake_agent(runner, work(repo, "b.txt", "ok"))
        run_phase(runner, repo)
        assert [c[0] for c in calls] == [1]
        assert read_index(repo)["steps"][0]["completed_at"] == "2026-01-01T00:00:00+0900"

    def test_step_reset_to_pending_after_ac_change_reruns(self, runner, repo):
        """복구 안내: AC를 고치면 완료된 step도 pending으로 되돌린다. 남아 있는 옛 completed_at은 확정이 아니다."""
        report(repo, 0, "pending", summary="old", completed_at="2026-01-01T00:00:00+0900")
        calls = fake_agent(runner, work(repo, "a.txt", "ok"), work(repo, "b.txt", "ok"))
        run_phase(runner, repo)
        assert [c[0] for c in calls] == [0, 1]
        assert read_index(repo)["steps"][0]["completed_at"] != "2026-01-01T00:00:00+0900"

    def test_finalize_requires_every_step_confirmed(self, runner, repo):
        report(repo, 0, "completed", summary="x", completed_at="2026-01-01T00:00:00+0900")
        report(repo, 1, "completed", summary="y")
        with pytest.raises(SystemExit) as e:
            runner._finalize()
        assert e.value.code == 1
        assert "completed_at" not in read_index(repo)
        assert log(repo) == ["init"]
