"""
tdd_guard.py 테스트.
규칙 판정(check)과 hook 입출력(main, exit 코드)을 함께 검증한다.
"""

import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import tdd_guard as tg

GUARD = Path(__file__).parent / "tdd_guard.py"


def touch(root: Path, rel: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("")


def check(root: Path, rel: str):
    return tg.check(PurePosixPath(rel), root)


def run_hook(project: Path, payload, cwd: Path = None):
    """hook을 실제 프로세스로 실행하고 (exit 코드, stderr)를 돌려준다."""
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    r = subprocess.run(
        [sys.executable, str(GUARD)], input=stdin, capture_output=True,
        text=True, env=env, cwd=str(cwd or project),
    )
    return r.returncode, r.stderr


def edit(path, cwd):
    return {"tool_input": {"file_path": str(path)}, "cwd": str(cwd)}


# ---------------------------------------------------------------------------
# JS/TS
# ---------------------------------------------------------------------------

class TestJsTs:
    def test_denies_without_test(self, tmp_path):
        reason = check(tmp_path, "src/lib/foo.ts")
        assert reason and "src/lib/foo.test.ts" in reason

    @pytest.mark.parametrize("test_rel", [
        "src/lib/foo.test.ts",
        "src/lib/foo.spec.tsx",
        "src/lib/foo.test.js",
        "src/lib/__tests__/foo.test.ts",
    ])
    def test_allows_with_paired_test(self, tmp_path, test_rel):
        touch(tmp_path, test_rel)
        assert check(tmp_path, "src/lib/foo.ts") is None

    @pytest.mark.parametrize("rel", [
        "src/lib/foo.test.ts",
        "src/lib/foo.spec.tsx",
        "src/__tests__/helpers.ts",
        "test/helpers.js",
        "__mocks__/axios.js",
        "src/__mocks__/api.ts",
    ])
    def test_test_side_files_allowed(self, tmp_path, rel):
        assert check(tmp_path, rel) is None

    @pytest.mark.parametrize("rel", [
        "src/types/user.ts",
        "src/types.ts",
        "src/global.d.ts",
        "vitest.config.ts",
        "next.config.mjs",
        "src/app/layout.tsx",
        "src/app/page.tsx",
        "src/app/loading.tsx",
        "src/app/error.tsx",
        "src/app/not-found.tsx",
        "src/app/page.js",
        "src/app/layout.jsx",
        "src/app/loading.ts",
        "src/app/error.js",
        "src/app/not-found.jsx",
        "src/main.tsx",
        "electron/main.js",
    ])
    def test_exempt(self, tmp_path, rel):
        assert check(tmp_path, rel) is None

    @pytest.mark.parametrize("rel", ["src/app/pages.js", "src/lib/error-utils.ts"])
    def test_nextjs_exemption_needs_exact_name(self, tmp_path, rel):
        assert check(tmp_path, rel) is not None

    @pytest.mark.parametrize("rel", ["vitest.setup.ts", "jest.setup.js", "src/setupTests.ts"])
    def test_test_setup_files_exempt(self, tmp_path, rel):
        assert check(tmp_path, rel) is None

    @pytest.mark.parametrize("rel", ["src/lib/setup.ts", "src/lib/setup-db.ts", "src/lib/db.setup.ts"])
    def test_test_setup_exemption_needs_exact_name(self, tmp_path, rel):
        assert check(tmp_path, rel) is not None

    @pytest.mark.parametrize("rel", ["src/lib/latest.ts", "src/lib/inspector.ts"])
    def test_name_containing_test_or_spec_is_not_exempt(self, tmp_path, rel):
        # 기존 가드는 *test*, *spec* 매칭으로 이 파일들을 통과시켰다.
        assert check(tmp_path, rel) is not None

    def test_parent_tests_dir_with_same_name_does_not_count(self, tmp_path):
        touch(tmp_path, "src/__tests__/foo.test.ts")
        assert check(tmp_path, "src/lib/foo.ts") is not None

    @pytest.mark.parametrize("ext", [".tsx", ".js", ".jsx", ".mjs", ".cjs"])
    def test_all_js_extensions_guarded(self, tmp_path, ext):
        assert check(tmp_path, f"src/lib/foo{ext}") is not None


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

class TestPython:
    def test_denies_without_test(self, tmp_path):
        reason = check(tmp_path, "app/service.py")
        assert reason and "app/test_service.py" in reason
        assert "tests/app/test_service.py" in reason

    @pytest.mark.parametrize("test_rel", [
        "app/test_service.py",
        "app/service_test.py",
        "app/tests/test_service.py",
        "tests/app/test_service.py",
    ])
    def test_allows_with_paired_test(self, tmp_path, test_rel):
        touch(tmp_path, test_rel)
        assert check(tmp_path, "app/service.py") is None

    def test_src_prefix_is_stripped_in_mirror(self, tmp_path):
        touch(tmp_path, "tests/users/test_service.py")
        assert check(tmp_path, "src/users/service.py") is None

    def test_same_basename_in_other_module_does_not_count(self, tmp_path):
        touch(tmp_path, "tests/users/test_service.py")
        assert check(tmp_path, "src/orders/service.py") is not None

    def test_flat_tests_dir_does_not_count(self, tmp_path):
        touch(tmp_path, "tests/test_service.py")
        assert check(tmp_path, "app/service.py") is not None

    def test_flat_tests_dir_counts_for_root_module(self, tmp_path):
        touch(tmp_path, "tests/test_main.py")
        assert check(tmp_path, "main.py") is None

    @pytest.mark.parametrize("rel", [
        "app/test_service.py",
        "app/service_test.py",
        "tests/helpers.py",
        "app/tests/factories.py",
        "test/helpers.py",
    ])
    def test_test_side_files_allowed(self, tmp_path, rel):
        assert check(tmp_path, rel) is None

    @pytest.mark.parametrize("rel", [
        "app/__init__.py",
        "conftest.py",
        "setup.py",
        "app/migrations/0001_initial.py",
        "src/pkg/__main__.py",
    ])
    def test_exempt(self, tmp_path, rel):
        assert check(tmp_path, rel) is None

    def test_main_py_still_guarded(self, tmp_path):
        # FastAPI 등에서 main.py는 라우트 같은 로직을 담는다.
        assert check(tmp_path, "app/main.py") is not None

    def test_directory_exempt_matches_whole_component(self, tmp_path):
        assert check(tmp_path, "app/my_migrations_util.py") is not None


class TestOtherFiles:
    @pytest.mark.parametrize("rel", ["README.md", "package.json", "src/app/globals.css", "main.go"])
    def test_unknown_extensions_not_guarded(self, tmp_path, rel):
        assert check(tmp_path, rel) is None


# ---------------------------------------------------------------------------
# 이미 있는 파일 (스캐폴딩 도구가 만든 파일, 기존 코드)
# ---------------------------------------------------------------------------

class TestExistingFiles:
    @pytest.mark.parametrize("rel", ["src/main.tsx", "src/lib/foo.ts", "app/service.py", "myproj/settings.py"])
    def test_existing_file_without_test_allowed(self, tmp_path, rel):
        touch(tmp_path, rel)
        assert check(tmp_path, rel) is None

    def test_new_file_beside_existing_one_still_guarded(self, tmp_path):
        touch(tmp_path, "src/lib/foo.ts")
        assert check(tmp_path, "src/lib/bar.ts") is not None

    def test_directory_with_impl_name_still_guarded(self, tmp_path):
        (tmp_path / "src" / "lib" / "foo.ts").mkdir(parents=True)
        assert check(tmp_path, "src/lib/foo.ts") is not None


# ---------------------------------------------------------------------------
# hook 입출력 (실제 프로세스)
# ---------------------------------------------------------------------------

class TestMain:
    def test_deny_exits_2_with_reason(self, tmp_path):
        code, err = run_hook(tmp_path, edit(tmp_path / "src/lib/foo.ts", tmp_path))
        assert code == 2
        assert "foo.test.ts" in err

    def test_allow_exits_0(self, tmp_path):
        touch(tmp_path, "src/lib/foo.test.ts")
        code, _ = run_hook(tmp_path, edit(tmp_path / "src/lib/foo.ts", tmp_path))
        assert code == 0

    @pytest.mark.parametrize("rel", ["src/App.tsx", "app/service.py"])
    def test_existing_file_exits_0(self, tmp_path, rel):
        touch(tmp_path, rel)
        code, _ = run_hook(tmp_path, edit(tmp_path / rel, tmp_path))
        assert code == 0

    def test_relative_path_resolved_from_cwd(self, tmp_path):
        (tmp_path / "src").mkdir()
        code, err = run_hook(tmp_path, edit("lib/foo.py", tmp_path / "src"))
        assert code == 2
        assert "src/lib/test_foo.py" in err

    def test_dotdot_is_normalized(self, tmp_path):
        touch(tmp_path, "app/test_service.py")
        path = tmp_path / "app" / "sub" / ".." / "service.py"
        code, _ = run_hook(tmp_path, edit(path, tmp_path))
        assert code == 0

    def test_outside_project_allowed(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        code, _ = run_hook(project, edit(tmp_path / "elsewhere" / "foo.py", project))
        assert code == 0

    def test_symlink_to_outside_allowed(self, tmp_path):
        project, outside = tmp_path / "proj", tmp_path / "outside"
        project.mkdir()
        outside.mkdir()
        (outside / "foo.py").write_text("")
        (project / "link.py").symlink_to(outside / "foo.py")
        code, _ = run_hook(project, edit(project / "link.py", project))
        assert code == 0

    def test_project_name_containing_test_still_guarded(self, tmp_path):
        project = tmp_path / "contest-app"
        project.mkdir()
        code, _ = run_hook(project, edit(project / "src" / "foo.ts", project))
        assert code == 2

    def test_path_with_spaces(self, tmp_path):
        project = tmp_path / "my project"
        project.mkdir()
        touch(project, "my app/test_main.py")
        code, _ = run_hook(project, edit(project / "my app" / "main.py", project))
        assert code == 0

    def test_project_dir_symlinked_like_macos_tmp(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        alias = tmp_path / "alias"
        alias.symlink_to(real)
        # CLAUDE_PROJECT_DIR는 별칭, file_path는 실제 경로로 들어와도 프로젝트 안으로 판단한다.
        code, _ = run_hook(alias, edit(real / "app" / "foo.py", real))
        assert code == 2

    def test_no_file_path_allowed(self, tmp_path):
        code, _ = run_hook(tmp_path, {"tool_input": {}, "cwd": str(tmp_path)})
        assert code == 0

    def test_invalid_json_is_non_blocking_error(self, tmp_path):
        code, err = run_hook(tmp_path, "{not json")
        assert code == 1
        assert err
