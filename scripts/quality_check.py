from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    name: str
    command: list[str]
    cwd: Path


def run_check(check: Check) -> bool:
    print(f"\n==> {check.name}")
    print("    " + " ".join(check.command))
    try:
        subprocess.run(check.command, cwd=check.cwd, check=True)
    except FileNotFoundError:
        print(f"    ERROR: command not found: {check.command[0]}")
        return False
    except subprocess.CalledProcessError as exc:
        print(f"    ERROR: command exited with code {exc.returncode}")
        return False

    print("    OK")
    return True


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    frontend_dir = repo_root / "app" / "frontend"
    backend_dir = repo_root / "app" / "backend"
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    python_cmd = sys.executable

    checks = [
        Check(name="Frontend lint", command=[npm_cmd, "run", "lint"], cwd=frontend_dir),
        Check(name="Frontend typecheck", command=[npm_cmd, "run", "typecheck"], cwd=frontend_dir),
        Check(name="Frontend format check", command=[npm_cmd, "run", "format:check"], cwd=frontend_dir),
        Check(name="Frontend tests", command=[npm_cmd, "run", "test"], cwd=frontend_dir),
        Check(
            name="Backend lint",
            command=[python_cmd, "-m", "flake8", "--jobs", "1", "src", "tests"],
            cwd=backend_dir,
        ),
        Check(
            name="Backend format check",
            command=[python_cmd, "-m", "black", "--check", "src", "tests"],
            cwd=backend_dir,
        ),
        Check(name="Backend tests", command=[python_cmd, "-m", "pytest", "-q"], cwd=backend_dir),
    ]

    failed_checks: list[str] = []
    for check in checks:
        if not run_check(check):
            failed_checks.append(check.name)

    print("\n==> Quality Summary")
    if failed_checks:
        print("    FAILED checks:")
        for name in failed_checks:
            print(f"    - {name}")
        return 1

    print("    All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
