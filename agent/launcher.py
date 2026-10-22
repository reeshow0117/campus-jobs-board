"""先加载私有环境文件，再导入服务，避免配置在导入时遗漏。"""
import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description="启动独立简历系统")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not args.env_file.is_file():
        parser.error("私有配置文件不存在；先运行 scripts/local_setup.py")
    load_dotenv(args.env_file, override=False)
    if os.environ.get("QIUZHAO_PRIVATE_VAULT") == "1":
        parser.error("此入口使用邀请模式，请移除 QIUZHAO_PRIVATE_VAULT=1")
    from . import server
    sys.argv = [sys.argv[0], "--host", "127.0.0.1", "--port", str(args.port)]
    server.main()


if __name__ == "__main__":
    main()
