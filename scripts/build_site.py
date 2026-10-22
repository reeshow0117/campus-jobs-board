#!/usr/bin/env python3
"""从 web/ 模板和 data/ 岗位快照构建 dist/ 静态站点。"""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.public_config import javascript


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume-only", action="store_true", help="构建独立简历站至 dist/resume-app")
    args = ap.parse_args()
    if args.resume_only:
        destination = ROOT / "dist/resume-app"
        destination.mkdir(parents=True, exist_ok=True)
        for name in ("index.html", "resume.html"):
            shutil.copyfile(ROOT / "web/resume.html", destination / name)
        shutil.copyfile(ROOT / "web/resume.css", destination / "resume.css")
        subprocess.run([sys.executable, str(ROOT / "data/build_jobs_slim.py")], cwd=ROOT, check=True)
        shutil.copyfile(ROOT / "dist/jobs_slim.json", destination / "jobs_slim.json")
        (destination / "config.js").write_text(javascript(), encoding="utf-8")
        print("resume site built:", destination)
        return
    if not (ROOT / "dist").is_dir():
        (ROOT / "dist").mkdir()
    subprocess.run([sys.executable, str(ROOT / "data/build_dashboard.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "data/build_jobs_slim.py")], cwd=ROOT, check=True)
    shutil.copyfile(ROOT / "秋招岗位看板.html", ROOT / "dist/index.html")
    shutil.copyfile(ROOT / "web/resume.html", ROOT / "dist/resume.html")
    shutil.copyfile(ROOT / "web/resume.css", ROOT / "dist/resume.css")
    (ROOT / "dist/config.js").write_text(javascript(), encoding="utf-8")
    print("site built:", ROOT / "dist")


if __name__ == "__main__":
    main()
