"""Create clean MyGraphWar release exports from the development workspace.

The default export is Release-Project: authored source files and project
configuration only. Installed dependencies, builds, databases, caches and
local runtime data are never copied.

Release-App is intentionally reserved for a later standalone distribution
pipeline. Running with --app currently reports that it is not implemented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECT_NAME = "Release-Project"
APP_NAME = "Release-App"

ROOT_FILES = {
    ".env.example",
    ".gitignore",
    "backup.ps1",
    "FIDELITY.md",
    "PLAN.md",
    "pytest.ini",
    "README.md",
    "Release.py",
    "requirements.txt",
    "run.py",
    "start.cmd",
    "start.ps1",
    "TODO.md",
    "verify.ps1",
}
SOURCE_DIRS = {"server", "tests", "web"}
EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "backups",
    "dist",
    "node_modules",
    "playwright-report",
    PROJECT_NAME,
    APP_NAME,
    "test-results",
}
EXCLUDED_SUFFIXES = {".db", ".log", ".pyc", ".pyo", ".tmp"}
EXCLUDED_FILES = {".env", ".coverage", "coverage.xml", "tsconfig.tsbuildinfo"}


def is_project_file(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    if path.name in EXCLUDED_FILES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if len(relative.parts) == 1:
        return path.name in ROOT_FILES
    return relative.parts[0] in SOURCE_DIRS


def collect_project_files() -> list[Path]:
    files = []
    for current, directories, names in os.walk(ROOT):
        directories[:] = [name for name in directories if name not in EXCLUDED_DIRS]
        for name in names:
            path = Path(current) / name
            if is_project_file(path):
                files.append(path)
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix().lower())


def safe_remove(target: Path, output_root: Path) -> None:
    resolved_target = target.resolve()
    resolved_output = output_root.resolve()
    if resolved_target.parent != resolved_output or resolved_target.name not in {PROJECT_NAME, APP_NAME, f".{PROJECT_NAME}.tmp"}:
        raise RuntimeError(f"Refusing to remove unexpected path: {resolved_target}")
    if target.exists():
        shutil.rmtree(target)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_project(output_root: Path, dry_run: bool = False) -> Path:
    output_root = output_root.resolve()
    target = output_root / PROJECT_NAME
    files = collect_project_files()
    if dry_run:
        print(f"Would export {len(files)} files to {target}")
        for source in files:
            print(source.relative_to(ROOT).as_posix())
        return target

    output_root.mkdir(parents=True, exist_ok=True)
    temporary = output_root / f".{PROJECT_NAME}.tmp"
    safe_remove(temporary, output_root)
    temporary.mkdir()
    try:
        manifest_files = []
        for source in files:
            relative = source.relative_to(ROOT)
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            manifest_files.append({
                "path": relative.as_posix(),
                "size": destination.stat().st_size,
                "sha256": sha256(destination),
            })
        manifest = {
            "format": 1,
            "kind": "source-project",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_count": len(manifest_files),
            "files": manifest_files,
            "excluded": [
                "installed dependencies (.venv, node_modules)",
                "generated builds (web/dist)",
                "runtime data (*.db, backups, .env)",
                "test/build caches and reports",
            ],
        }
        (temporary / "RELEASE-MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        safe_remove(target, output_root)
        temporary.rename(target)
    except Exception:
        safe_remove(temporary, output_root)
        raise
    print(f"Release-Project created: {target}")
    print(f"Exported {len(files)} project files; local dependencies, builds and data were excluded.")
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export clean MyGraphWar release folders.")
    parser.add_argument("--project", action="store_true", help="Export the clean source project (default).")
    parser.add_argument("--app", action="store_true", help="Build Release-App (reserved; not implemented yet).")
    parser.add_argument("--output-root", type=Path, default=ROOT, help="Parent directory for release folders.")
    parser.add_argument("--dry-run", action="store_true", help="List files without creating an export.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.app:
        print("Release-App packaging is reserved for the future standalone distribution pipeline.", file=sys.stderr)
        print("No incomplete Release-App folder was created.", file=sys.stderr)
        return 2
    export_project(args.output_root, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
