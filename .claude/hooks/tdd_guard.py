#!/usr/bin/env python3
"""
TDD Guard Hook — PreToolUse[Edit|Write]

새 구현 파일을 만들기 전에 짝 테스트 파일이 있는지 확인한다. 없으면 exit 2로 막는다.
이미 있는 파일(스캐폴딩 도구가 만든 파일, 기존 코드)은 Edit든 Write 덮어쓰기든 검사하지 않는다.
그래서 짝 테스트를 지운 뒤의 구현 파일 수정과, Bash로 만든 파일의 이후 Edit도 통과한다.
테스트 파일이 '있는지'만 본다. 실제 동작 검증은 execute.py의 AC 게이트가 맡는다.
Bash로 쓰는 파일은 범위 밖이다.

exit 0: 통과 / exit 2: 차단(stderr가 Claude에게 전달됨) / exit 1: hook 내부 오류(비차단)
"""

import json
import os
import sys
from pathlib import Path, PurePosixPath
from typing import List, Optional

TEST_DIRS = {"tests", "__tests__", "test", "__mocks__"}

JS_EXTS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]
JS_EXEMPT_NAMES = {"types.ts"}
# Next.js 프레임워크 파일. 확장자와 상관없이 이름으로 면제한다.
JS_EXEMPT_STEMS = {"layout", "page", "loading", "error", "not-found"}
# 엔트리포인트. 렌더링·실행만 하고 단위 테스트할 동작이 없다.
JS_ENTRY_STEMS = {"main"}
# 테스트 환경 설정 파일. 구현이 아니라 테스트 쪽 파일이다.
JS_TEST_SETUP_STEMS = {"vitest.setup", "jest.setup", "setupTests"}
JS_EXEMPT_DIRS = {"types"}

PY_EXEMPT_NAMES = {"__init__.py", "__main__.py", "conftest.py", "setup.py"}
PY_EXEMPT_DIRS = {"migrations"}


def _js_candidates(rel: PurePosixPath, ext: str) -> Optional[List[PurePosixPath]]:
    """검사 대상이면 짝 테스트 후보 목록, 테스트 파일이거나 면제면 None."""
    name = rel.name
    stem = name[: -len(ext)]
    if ".test." in name or ".spec." in name or stem in JS_TEST_SETUP_STEMS:
        return None
    if name in JS_EXEMPT_NAMES or stem in JS_EXEMPT_STEMS | JS_ENTRY_STEMS or name.endswith(".d.ts") or ".config." in name:
        return None
    if JS_EXEMPT_DIRS & set(rel.parent.parts):
        return None
    d = rel.parent
    out = []
    for e in JS_EXTS:
        out += [d / f"{stem}.test{e}", d / f"{stem}.spec{e}", d / "__tests__" / f"{stem}.test{e}"]
    return out


def _py_candidates(rel: PurePosixPath) -> Optional[List[PurePosixPath]]:
    name = rel.name
    stem = name[:-3]
    if name.startswith("test_") or name.endswith("_test.py"):
        return None
    if name in PY_EXEMPT_NAMES or PY_EXEMPT_DIRS & set(rel.parent.parts):
        return None
    d = rel.parent
    mirror = d.parts[1:] if d.parts[:1] == ("src",) else d.parts
    return [
        d / f"test_{stem}.py",
        d / f"{stem}_test.py",
        d / "tests" / f"test_{stem}.py",
        PurePosixPath("tests", *mirror, f"test_{stem}.py"),
    ]


def check(rel: PurePosixPath, root: Path) -> Optional[str]:
    """rel(프로젝트 루트 기준 상대경로)을 막아야 하면 사유를, 아니면 None을 돌려준다."""
    if (root / rel).is_file() or TEST_DIRS & set(rel.parent.parts):
        return None

    ext = rel.suffix
    if ext in JS_EXTS:
        candidates = _js_candidates(rel, ext)
        expected = [f"{rel.parent / rel.stem}.test{ext}"] if candidates else []
    elif ext == ".py":
        candidates = _py_candidates(rel)
        expected = [str(candidates[0]), str(candidates[-1])] if candidates else []
    else:
        return None

    if candidates is None or any((root / c).is_file() for c in candidates):
        return None
    return (
        f"TDD GUARD: '{rel}'의 테스트 파일이 없습니다. "
        f"구현 코드를 쓰기 전에 테스트를 먼저 작성하세요. "
        f"(테스트 파일 예: {' 또는 '.join(expected)})"
    )


def to_rel(file_path: str, cwd: str, project: str) -> Optional[PurePosixPath]:
    """file_path를 프로젝트 루트 기준 상대경로로 바꾼다. 프로젝트 밖이면 None."""
    p = Path(file_path)
    if not p.is_absolute():
        p = Path(cwd) / p
    real = Path(os.path.realpath(p))
    root = Path(os.path.realpath(project))
    try:
        return PurePosixPath(real.relative_to(root).as_posix())
    except ValueError:
        return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
        file_path = (data.get("tool_input") or {}).get("file_path")
        if not file_path:
            return 0
        cwd = data.get("cwd") or os.getcwd()
        project = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
        rel = to_rel(file_path, cwd, project)
        reason = check(rel, Path(os.path.realpath(project))) if rel else None
    except Exception as e:
        print(f"tdd_guard 내부 오류(검사 생략): {e}", file=sys.stderr)
        return 1

    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
