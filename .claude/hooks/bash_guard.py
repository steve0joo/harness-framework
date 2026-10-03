#!/usr/bin/env python3
"""
Bash Guard Hook — PreToolUse[Bash]

되돌리기 어려운 명령(rm -rf, git push --force, git reset --hard, git clean -f, DROP TABLE/DATABASE)을 막는다.
실수 방지용 휴리스틱이며 보안 경계가 아니다. `bash -c "..."`처럼 따옴표로 감싼 명령은 잡지 못한다.
execute.py도 AC 명령 검사에 find_danger()를 재사용한다.

exit 0: 통과 / exit 2: 차단(stderr가 Claude에게 전달됨) / exit 1: hook 내부 오류(비차단)
"""

import json
import os
import re
import shlex
import sys
from typing import List, Optional

SQL_RE = re.compile(r"\bDROP\s+(TABLE|DATABASE)\b", re.IGNORECASE)
PUNCT = set("();<>|&")


def _tokenize(command: str) -> List[str]:
    """따옴표 안 문자열은 토큰 하나로 묶는다. 따옴표 짝이 맞지 않으면 보수적으로 단순 분리한다."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return re.findall(r"[^\s;&|()<>]+|[;&|()<>]+", command)


def _is_sep(token: str) -> bool:
    return all(c in PUNCT for c in token)


def _args_after(tokens: List[str], i: int) -> List[str]:
    out = []
    for t in tokens[i + 1:]:
        if _is_sep(t):
            break
        out.append(t)
    return out


def _short_flags(args: List[str]) -> str:
    return "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))


def _rm_danger(args: List[str]) -> bool:
    flags = _short_flags(args)
    recursive = "--recursive" in args or "r" in flags or "R" in flags
    force = "--force" in args or "f" in flags
    return recursive and force


def _git_danger(args: List[str]) -> Optional[str]:
    i = 0
    while i < len(args):
        if args[i] in ("-C", "-c"):
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            break
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if sub == "push" and ("--force" in rest or "-f" in rest):
        return "git push --force"
    if sub == "reset" and "--hard" in rest:
        return "git reset --hard"
    if sub == "clean" and ("--force" in rest or "f" in _short_flags(rest)):
        return "git clean -f"
    return None


def find_danger(command: str) -> Optional[str]:
    """위험한 명령이면 사유를, 아니면 None을 돌려준다."""
    if SQL_RE.search(command):
        return "DROP TABLE/DATABASE"
    tokens = _tokenize(command)
    for i, tok in enumerate(tokens):
        name = os.path.basename(tok)
        if name == "rm" and _rm_danger(_args_after(tokens, i)):
            return "rm -rf"
        if name == "git":
            reason = _git_danger(_args_after(tokens, i))
            if reason:
                return reason
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
        command = (data.get("tool_input") or {}).get("command") or ""
        reason = find_danger(command)
    except Exception as e:
        print(f"bash_guard 내부 오류(검사 생략): {e}", file=sys.stderr)
        return 1

    if reason:
        print(f"BLOCKED: 위험한 명령어가 감지되었습니다 ({reason}). 필요하면 사용자가 직접 실행하세요.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
