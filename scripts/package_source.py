"""Create a Canvas-ready source archive of every tracked project file.

The file list comes from git, so new folders are included automatically and
local dependencies, databases, recordings and credentials (all git-ignored)
are never packaged.
"""
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ELEC5620-Stage2-Source.zip"
EXCLUDE = {OUTPUT.name}
REQUIRED = ["README.md", "requirements.txt", "backend/main.py", "frontend/package.json", "migrations/env.py", "compose.yaml"]


def tracked_files() -> list[Path]:
    names = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout.decode("utf-8").split("\0")
    return [ROOT / name for name in names if name and name not in EXCLUDE]


def run():
    paths = tracked_files()
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()] + [str(p.relative_to(ROOT)) for p in paths if not p.is_file()]
    if missing:
        raise SystemExit(f"Missing source files: {missing}")
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(paths):
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(f"Packaged {len(paths)} files to {OUTPUT.name} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    run()
