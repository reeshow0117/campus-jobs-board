#!/usr/bin/env python3
"""从 web/ 模板和 data/ 岗位快照构建 dist/ 静态站点。"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not (ROOT / "dist").is_dir():
        (ROOT / "dist").mkdir()
    subprocess.run([sys.executable, str(ROOT / "data/build_dashboard.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "data/build_jobs_slim.py")], cwd=ROOT, check=True)
    shutil.copyfile(ROOT / "秋招岗位看板.html", ROOT / "dist/index.html")
    shutil.copyfile(ROOT / "web/resume.html", ROOT / "dist/resume.html")
    print("site built:", ROOT / "dist")


if __name__ == "__main__":
    main()
