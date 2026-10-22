"""在已有 Lighthouse 服务上部署固定提交；保留私有环境、SQLite 和管理员扩展。

只复用原服务的依赖环境，不修改防火墙、隧道或凭据。健康检查失败自动切回旧版本。
"""
import argparse
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
import zipfile


def preserve_admin_extensions(old_source, new_source):
    """保留服务器上已存在且在本交付包中缺失的管理员邀请功能。"""
    old, new = ast.parse(old_source), ast.parse(new_source)
    names = {n.name for n in new.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    extra = [n for n in old.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name not in names]
    if any("admin" not in n.name.lower() for n in extra):
        raise ValueError("存在未审阅的线上扩展：" + ", ".join(n.name for n in extra))
    if not extra:
        return new_source, []
    new_assignments = {t.id for n in new.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    assignments = [n for n in old.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and "admin" in t.id.lower()
                           and t.id not in new_assignments for t in n.targets)]
    imports = [n for n in old.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    new.body[1:1] = imports
    # 管理员能力展示保留原有判断，生成服务和额度检查仍使用本地版本。
    old_cap = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == "capabilities")
    new_cap = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == "capabilities")
    old_return = next(n for n in ast.walk(old_cap) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict))
    new_return = next(n for n in ast.walk(new_cap) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict))
    for key, value in zip(old_return.value.keys, old_return.value.values):
        if isinstance(key, ast.Constant) and key.value == "admin_invite":
            new_return.value.keys.append(key)
            new_return.value.values.append(value)
    index = next((i for i, n in enumerate(new.body) if isinstance(n, ast.If)
                  and "__name__" in ast.unparse(n.test)), len(new.body))
    new.body[index:index] = assignments + extra
    return ast.unparse(ast.fix_missing_locations(new)) + "\n", [n.name for n in extra]


def service_env(env_file):
    result = dict(os.environ)
    inline = subprocess.check_output(["systemctl", "show", "resume-platform", "--value", "-p", "Environment"], text=True)
    for value in shlex.split(inline):
        if "=" in value:
            key, val = value.split("=", 1)
            result[key] = val
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = shlex.split(line, comments=True)
        if parts and "=" in parts[0]:
            key, value = parts[0].split("=", 1)
            result[key] = value
    if result.get("QIUZHAO_PRIVATE_VAULT") == "1":
        raise ValueError("公开服务不得开启私人库模式")
    return result


def health():
    with urllib.request.urlopen("http://127.0.0.1:8000/api/capabilities", timeout=5) as response:
        caps = json.load(response)
    if caps.get("private_vault") or not caps.get("invite_required") or not caps.get("llm"):
        raise RuntimeError("身份边界校验失败")
    with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=5) as response:
        if "简历工作台" not in response.read().decode("utf-8"):
            raise RuntimeError("首页尚未更新")
    with urllib.request.urlopen("http://127.0.0.1:8000/resume.css", timeout=5) as response:
        if response.status != 200:
            raise RuntimeError("样式加载失败")
    for route, payload in (("/api/resume", {"title": "部署检查"}),
                           ("/api/resume_pdf", {"markdown": "# 部署检查简历\n\n虚构内容，不发往模型"})):
        request = urllib.request.Request("http://127.0.0.1:8000" + route,
                                         data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5):
                raise RuntimeError("匿名接口未被拒绝")
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise RuntimeError("匿名接口状态异常") from exc
    return caps


def activate(current, release):
    temporary = current.with_name(".next-" + release.name)
    if temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(release, target_is_directory=True)
    os.replace(temporary, current)
    subprocess.run(["systemctl", "restart", "resume-platform"], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--root", type=Path, default=Path("/opt/resume-platform"))
    parser.add_argument("--env-file", type=Path, default=Path("/etc/resume-platform.env"))
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        parser.error("必须使用完整提交 SHA")
    current = args.root / "current"
    if not current.is_symlink():
        raise RuntimeError("current 不是既有版本符号链接，未修改生产服务")
    previous = current.resolve(strict=True)
    release = args.root / "releases" / args.commit[:12]
    if release.exists():
        raise RuntimeError("候选版本目录已存在，请先检查上一次部署结果")
    release.mkdir(parents=True, mode=0o755)
    archive = release / "source.zip"
    print("Downloading fixed commit", args.commit, flush=True)
    with urllib.request.urlopen("https://codeload.github.com/reeshow0117/campus-jobs-board/zip/" + args.commit, timeout=60) as src, archive.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            rel = PurePosixPath(*PurePosixPath(item.filename).parts[1:])
            if not rel.parts or rel.is_absolute() or ".." in rel.parts or item.is_dir():
                continue
            if rel.parts[0] not in {"agent", "web", "dist", "scripts", "tests", "pyproject.toml", "README.md"}:
                continue
            destination = release.joinpath(*rel.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(bundle.read(item))
    server_file = release / "agent/server.py"
    merged, preserved = preserve_admin_extensions((previous / "agent/server.py").read_text(), server_file.read_text())
    server_file.write_text(merged)
    for name in ("admin.html",):
        original = previous / "web" / name
        if original.is_file() and not (release / "web" / name).exists():
            shutil.copyfile(original, release / "web" / name)
    (release / ".venv").symlink_to(previous / ".venv", target_is_directory=True)
    python = str(release / ".venv/bin/python")
    env = service_env(args.env_file)
    check = "from pathlib import Path; from agent import server,resume_pdf; assert Path(server.__file__).resolve().parent.parent == Path.cwd().resolve(); resume_pdf.register_fonts(); assert not server.PRIVATE_VAULT; server.access_store(); server.platform_model_limit(); print('Candidate preflight passed')"
    subprocess.run([python, "-c", check], cwd=release, env=env, check=True)
    manifest = {"commit": args.commit, "previous_release": str(previous), "preserved_extensions": preserved,
                "prepared_at": datetime.now(timezone.utc).isoformat()}
    (release / "deployment.json").write_text(json.dumps(manifest, indent=2))
    print("Prepared", release, "preserved:", ", ".join(preserved), flush=True)
    if not args.activate:
        print("Prepared only; live service unchanged")
        return
    database = Path(env["QIUZHAO_ACCESS_DB"])
    if not database.is_file():
        raise RuntimeError("既有邀请状态库不存在，未切换版本")
    backup_dir = database.parent / "deploy-backups"
    backup_dir.mkdir(exist_ok=True, mode=0o700)
    backup = backup_dir / (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".sqlite3")
    with sqlite3.connect(str(database)) as source, sqlite3.connect(str(backup)) as target:
        source.backup(target)
    backup.chmod(0o600)
    try:
        activate(current, release)
        for attempt in range(20):
            try:
                caps = health()
                break
            except (OSError, ValueError, RuntimeError):
                if attempt == 19:
                    raise
                time.sleep(0.5)
    except Exception:
        activate(current, previous)
        print("Deployment reverted to", previous, flush=True)
        raise
    print("Live service passed:", json.dumps(caps), flush=True)
    try:
        with urllib.request.urlopen("http://127.0.0.1:20241/quicktunnel", timeout=3) as response:
            hostname = json.load(response).get("hostname", "")
        if hostname:
            print("PUBLIC_URL https://" + hostname, flush=True)
    except (OSError, ValueError):
        pass


if __name__ == "__main__":
    main()
