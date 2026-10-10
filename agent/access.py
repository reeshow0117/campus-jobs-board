"""邀请制身份与持久化用量闸门。只保存随机凭据的 SHA-256 摘要，不存候选人资料。"""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import os
import re
import secrets
import sqlite3
import time
from urllib.parse import quote

CN_TZ = timezone(timedelta(hours=8))
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


class AccessError(Exception):
    def __init__(self, status, message, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class AccessStore:
    def __init__(self, path):
        self.path = os.path.abspath(path)

    def connect(self, create=False):
        mode = "rwc" if create else "rw"
        uri = "file:" + quote(self.path, safe="/") + "?mode=" + mode
        db = sqlite3.connect(uri, uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 5000")
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def init(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.commonpath((self.path, project_root)) == project_root:
            raise ValueError("访问状态库必须位于仓库外，避免将会话与用量数据提交到 Git")
        if not os.path.isdir(os.path.dirname(self.path)):
            raise ValueError("先创建仅服务账户可访问的状态目录")
        with closing(self.connect(create=True)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, label TEXT NOT NULL, created_at INTEGER NOT NULL,
                    revoked_at INTEGER, model_daily_quota INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS invites (
                    token_hash TEXT PRIMARY KEY, label TEXT NOT NULL,
                    expires_at INTEGER NOT NULL, redeemed_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL, revoked_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    kind TEXT NOT NULL, day TEXT NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS usage_lookup ON usage(user_id, kind, day, created_at);
            """)
        os.chmod(self.path, 0o600)

    def invite(self, label, days=7):
        label = label.strip()
        if not label or len(label) > 80 or not 1 <= days <= 30:
            raise ValueError("邀请备注需为 1-80 字，期限为 1-30 天")
        token = secrets.token_urlsafe(32)
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO invites VALUES (?, ?, ?, NULL)",
                       (digest(token), label, int(time.time()) + days * 86400))
        return token

    def redeem(self, token, default_quota):
        if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
            raise AccessError(403, "邀请码无效或已失效")
        now = int(time.time())
        session = secrets.token_urlsafe(32)
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            invite = db.execute("SELECT * FROM invites WHERE token_hash = ?", (digest(token),)).fetchone()
            if not invite or invite["redeemed_at"] is not None or invite["expires_at"] <= now:
                raise AccessError(403, "邀请码无效或已失效")
            user = db.execute("INSERT INTO users(label, created_at, model_daily_quota) VALUES (?, ?, ?)",
                              (invite["label"], now, default_quota))
            db.execute("UPDATE invites SET redeemed_at = ? WHERE token_hash = ?", (now, digest(token)))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, NULL)",
                       (digest(session), user.lastrowid, now + 30 * 86400))
        return session

    def user(self, session):
        if not isinstance(session, str) or not TOKEN_RE.fullmatch(session):
            raise AccessError(401, "请先使用邀请码登录")
        with closing(self.connect()) as db:
            row = db.execute("""SELECT users.id, users.model_daily_quota FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.revoked_at IS NULL
                AND sessions.expires_at > ? AND users.revoked_at IS NULL""",
                (digest(session), int(time.time()))).fetchone()
        if not row:
            raise AccessError(401, "登录已失效，请重新获取邀请")
        return row["id"]

    def consume(self, user_id, kind, per_minute=6):
        """每次 HTTP 请求/每次模型 HTTP 尝试都单独计数，跨进程 SQLite 原子提交。"""
        if kind not in ("request", "model"):
            raise ValueError("不支持的计费类型")
        now = int(time.time())
        day = datetime.fromtimestamp(now, CN_TZ).date().isoformat()
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute("SELECT model_daily_quota FROM users WHERE id = ? AND revoked_at IS NULL",
                              (user_id,)).fetchone()
            if not user:
                raise AccessError(401, "登录已失效")
            if kind == "request":
                oldest = db.execute("""SELECT MIN(created_at) AS first, COUNT(*) AS n FROM usage
                    WHERE user_id = ? AND kind = 'request' AND created_at > ?""",
                    (user_id, now - 60)).fetchone()
                if oldest["n"] >= per_minute:
                    raise AccessError(429, "操作太频繁，请稍后再试", max(1, oldest["first"] + 61 - now))
            else:
                count = db.execute("""SELECT COUNT(*) FROM usage
                    WHERE user_id = ? AND kind = 'model' AND day = ?""",
                    (user_id, day)).fetchone()[0]
                if count >= user["model_daily_quota"]:
                    raise AccessError(429, "今日模型调用额度已用完，请明天再试")
            db.execute("INSERT INTO usage(user_id, kind, day, created_at) VALUES (?, ?, ?, ?)",
                       (user_id, kind, day, now))

    def quota(self, user_id):
        day = datetime.now(CN_TZ).date().isoformat()
        with closing(self.connect()) as db:
            row = db.execute("SELECT model_daily_quota FROM users WHERE id = ? AND revoked_at IS NULL",
                             (user_id,)).fetchone()
            if not row:
                raise AccessError(401, "登录已失效")
            used = db.execute("""SELECT COUNT(*) FROM usage
                WHERE user_id = ? AND kind = 'model' AND day = ?""", (user_id, day)).fetchone()[0]
        return {"day": day, "model_calls_used": used,
                "model_calls_limit": row["model_daily_quota"],
                "model_calls_remaining": max(0, row["model_daily_quota"] - used)}

    def revoke(self, user_id):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("UPDATE users SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                          (int(time.time()), user_id)).rowcount != 1:
                raise ValueError("用户不存在或已撤销")
            db.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ?",
                       (int(time.time()), user_id))

    def set_quota(self, user_id, limit):
        if not 0 <= limit <= 10000:
            raise ValueError("额度必须在 0-10000 之间")
        with closing(self.connect()) as db, db:
            if db.execute("UPDATE users SET model_daily_quota = ? WHERE id = ? AND revoked_at IS NULL",
                          (limit, user_id)).rowcount != 1:
                raise ValueError("用户不存在或已撤销")


def main():
    ap = argparse.ArgumentParser(description="本地管理邀请与用量；不要把邀请码写入仓库或日志")
    ap.add_argument("--db", default=os.environ.get("QIUZHAO_ACCESS_DB"), required=False)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    invite = sub.add_parser("invite")
    invite.add_argument("--label", required=True, help="仅供管理员识别的备注，不填隐私资料")
    invite.add_argument("--days", type=int, default=7)
    revoke = sub.add_parser("revoke")
    revoke.add_argument("user_id", type=int)
    quota = sub.add_parser("quota")
    quota.add_argument("user_id", type=int)
    quota.add_argument("limit", type=int)
    args = ap.parse_args()
    if not args.db:
        ap.error("需指定 --db 或 QIUZHAO_ACCESS_DB（目录须位于仓库外）")
    store = AccessStore(args.db)
    if args.command == "init":
        store.init()
        print("状态库已初始化；请将目录限制为仅服务账户可访问")
    elif args.command == "invite":
        print("一次性邀请码（仅此一次显示，请私下传递）:", store.invite(args.label, args.days))
    elif args.command == "revoke":
        store.revoke(args.user_id)
        print("用户会话已撤销:", args.user_id)
    elif args.command == "quota":
        store.set_quota(args.user_id, args.limit)
        print("用户每日模型尝试额度已更新:", args.user_id)


if __name__ == "__main__":
    main()
