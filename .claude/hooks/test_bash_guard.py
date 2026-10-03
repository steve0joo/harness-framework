"""
bash_guard.py 테스트.
판정 함수(find_danger)와 hook 입출력(main, exit 코드)을 함께 검증한다.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import bash_guard as bg

GUARD = Path(__file__).parent / "bash_guard.py"


def run_hook(payload):
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    r = subprocess.run([sys.executable, str(GUARD)], input=stdin, capture_output=True, text=True)
    return r.returncode, r.stderr


BLOCKED = [
    "rm -rf dist",
    "rm -fr dist",
    "rm -Rf dist",
    "rm -rfv dist",
    "rm -r -f dist",
    "rm -f -r dist",
    "rm --recursive --force dist",
    "/bin/rm -rf dist",
    "sudo rm -Rf x",
    "cd a && rm -fr b",
    "cd a;rm -r -f b",
    "echo hi\nrm -rf x",
    "find . -name '*.tmp' | xargs rm -rf",
    "git push -f",
    "git push --force origin main",
    "git -C repo push --force origin main",
    "git reset --hard HEAD~1",
    "git clean -fd",
    "git clean -f",
    "bash <<'EOF'\nrm -rf x\nEOF",
    "git clean --force -d",
    'psql -c "drop table users"',
    "mysql -e 'DROP DATABASE app'",
]

ALLOWED = [
    'echo "rm -rf"',
    'git commit -m "remove rm -rf usage"',
    "rm -r dir",
    "rm -f file",
    "rm file",
    "git push --force-with-lease",
    "git push origin main",
    "git reset --soft HEAD~1",
    "git reset HEAD -- file",
    "git clean -n",
    "git status",
    "ls -la",
    "npm run build && npm test",
]

# 알면서 받아들이는 오탐: 차단되지만 감수한다 (계획 5-2).
ACCEPTED_FALSE_POSITIVES = [
    "echo rm -rf x",
    'git commit -m "fix DROP TABLE bug"',
    # heredoc 본문은 따옴표로 묶이지 않아 명령처럼 판정된다. 메시지는 -m "..."이나 -F <파일>로 넘긴다.
    "git commit -F - <<'EOF'\nadds git clean -f\nEOF",
]

# 알려진 한계: 따옴표로 감싼 명령은 잡지 못한다 (계획 5-2).
KNOWN_MISSES = [
    'bash -c "rm -rf x"',
]


class TestFindDanger:
    @pytest.mark.parametrize("cmd", BLOCKED)
    def test_blocked(self, cmd):
        assert bg.find_danger(cmd) is not None

    @pytest.mark.parametrize("cmd", ALLOWED)
    def test_allowed(self, cmd):
        assert bg.find_danger(cmd) is None

    @pytest.mark.parametrize("cmd", ACCEPTED_FALSE_POSITIVES)
    def test_accepted_false_positives(self, cmd):
        assert bg.find_danger(cmd) is not None

    @pytest.mark.parametrize("cmd", KNOWN_MISSES)
    def test_known_misses(self, cmd):
        assert bg.find_danger(cmd) is None

    def test_unbalanced_quote_falls_back_conservatively(self):
        assert bg.find_danger('echo "oops; rm -rf x') is not None
        assert bg.find_danger('echo "oops') is None


class TestMain:
    def test_blocked_exits_2_with_reason(self):
        code, err = run_hook({"tool_input": {"command": "rm -rf dist"}})
        assert code == 2
        assert "BLOCKED" in err

    def test_allowed_exits_0(self):
        code, _ = run_hook({"tool_input": {"command": "ls -la"}})
        assert code == 0

    def test_no_command_allowed(self):
        code, _ = run_hook({"tool_input": {}})
        assert code == 0

    def test_invalid_json_is_non_blocking_error(self):
        code, err = run_hook("{not json")
        assert code == 1
        assert err
