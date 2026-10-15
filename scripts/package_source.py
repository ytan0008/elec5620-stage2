"""Create a Canvas-ready source archive without local dependencies or data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ELEC5620-Stage2-Source.zip"
FILES = [
    ".env.example", ".gitignore", ".dockerignore", "README.md", "requirements.txt",
    "alembic.ini", "compose.yaml", "Dockerfile.backend",
    "ELEC5620_Wed_09-11 Group3.pdf",
    "frontend/package.json", "frontend/package-lock.json", "frontend/index.html",
    "frontend/Dockerfile", "frontend/.dockerignore", "frontend/nginx.conf", "frontend/tsconfig.json",
    "frontend/vite.config.ts", "frontend/postcss.config.js", "frontend/tailwind.config.js",
    "frontend/playwright.config.ts", "docs/IMPLEMENTATION_STATUS.md",
    "docs/agile-evidence.md", "docs/jira-backlog.csv",
    ".github/workflows/ci.yml", "scripts/package_source.py",
]


def run():
    paths = [ROOT / name for name in FILES]
    for folder, pattern in [("backend", "*.py"), ("tests", "*.py"), ("migrations", "*.py"), ("migrations", "*.mako"), ("migrations/versions", "*.py"), ("frontend/src", "*"), ("frontend/e2e", "*.ts")]:
        paths.extend((ROOT / folder).glob(pattern))
    missing = [str(path.relative_to(ROOT)) for path in paths if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing source files: {missing}")
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(set(paths)):
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(f"Packaged {len(set(paths))} files to {OUTPUT.name} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    run()
