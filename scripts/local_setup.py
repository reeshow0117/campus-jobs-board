"""准备仓库外本地配置和自用邀请码；密钥通过隐藏输入更新，不进入命令历史。"""
import argparse
import getpass
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.access import AccessStore
from dotenv import dotenv_values, set_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, default=ROOT.parent / ".resume-platform-local")
    parser.add_argument("--no-key", action="store_true", help="只准备配置，不输入模型密钥")
    args = parser.parse_args()
    state = args.state_dir.resolve()
    database = state / "access.sqlite3"
    store = AccessStore(str(database))  # 先校验不得在仓库内。
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not database.exists():
        store.init()
    env_path = state / ".env"
    if not env_path.exists():
        values = {
            "QIUZHAO_ACCESS_DB": database.as_posix(),
            "QIUZHAO_PLATFORM_MODEL_DAILY_LIMIT": "12",
            "QIUZHAO_MODEL_DAILY_LIMIT": "12",
            "QIUZHAO_LLM_BASE_URL": "https://api.deepseek.com",
            "QIUZHAO_LLM_MODEL": "deepseek-flash",
            "QIUZHAO_LLM_API_KEY": "",
            "QIUZHAO_CORS": "",
        }
        env_path.touch(mode=0o600)
        for name, value in values.items():
            set_key(str(env_path), name, value)
    if not args.no_key:
        key = getpass.getpass("DeepSeek API Key（隐藏输入，留空保留现有值）: ").strip()
        if key:
            if any(char.isspace() for char in key):
                parser.error("API Key 不应包含空白字符")
            set_key(str(env_path), "QIUZHAO_LLM_API_KEY", key)
    # 首次初始化签发一个自用邀请码；重复运行不覆盖，也不额外发码。
    invite_file = state / "owner-invite.txt"
    if not invite_file.exists():
        with invite_file.open("x", encoding="utf-8") as stream:
            stream.write(store.invite("owner", days=7) + "\n")
        os.chmod(invite_file, 0o600)
    print("私有配置:", env_path)
    print("自用邀请码文件（7 天内一次性兑换）:", invite_file)
    print("模型 Key:", "已配置" if dotenv_values(env_path).get("QIUZHAO_LLM_API_KEY") else "未配置，生成暂不可用")
    print("启动: python -m agent.launcher --env-file", '"' + str(env_path) + '"')


if __name__ == "__main__":
    main()
