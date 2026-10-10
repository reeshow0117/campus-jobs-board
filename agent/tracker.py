#!/usr/bin/env python3
"""投递状态追踪 CLI

状态库：agent/state/tracker.json（本机文件，不上传任何服务器）

用法:
  python3 agent/tracker.py add <岗位id> --status 已投 [--note "官网投递"]
  python3 agent/tracker.py add <岗位id> --status 笔试
  python3 agent/tracker.py list [--status 已投]
  python3 agent/tracker.py stats

状态机：未投 -> 已投 -> 笔试 -> 面试 -> offer / 已挂
"""
import argparse
import json
import os
import sys
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, "state", "tracker.json")

STATUSES = ["未投", "已投", "笔试", "面试", "offer", "已挂"]


def load_tracker():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_tracker(t):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)  # 原子写入，防中断写坏状态库


def main():
    ap = argparse.ArgumentParser(description="秋招投递状态追踪")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="记录/更新一条投递状态")
    p_add.add_argument("job_id", type=int)
    p_add.add_argument("--status", required=True, choices=STATUSES[1:])
    p_add.add_argument("--note", default="")

    p_list = sub.add_parser("list", help="列出追踪记录")
    p_list.add_argument("--status", choices=STATUSES[1:], default=None)

    sub.add_parser("stats", help="统计各状态数量")
    args = ap.parse_args()

    tracker = load_tracker()

    if args.cmd == "add":
        key = str(args.job_id)
        old = tracker.get(key, {})
        tracker[key] = {
            "status": args.status,
            "date": date.today().isoformat(),
            "note": args.note or old.get("note", ""),
            "history": old.get("history", []) + [
                {"status": args.status, "date": date.today().isoformat()}
            ],
        }
        save_tracker(tracker)
        print(f"已记录：岗位 #{args.job_id} -> {args.status}（共 {len(tracker)} 条）")

    elif args.cmd == "list":
        jobs_idx = {}
        merged = os.path.join(BASE, "..", "data", "jobs_merged.json")
        if os.path.exists(merged):
            with open(merged, encoding="utf-8") as f:
                for j in json.load(f)["jobs"]:
                    jobs_idx[str(j["id"])] = j
        rows = [(k, v) for k, v in tracker.items()
                if not args.status or v["status"] == args.status]
        rows.sort(key=lambda x: x[1]["date"], reverse=True)
        if not rows:
            print("暂无记录")
            return
        for k, v in rows:
            j = jobs_idx.get(k, {})
            print(f"#{k:>5} [{v['status']}] {v['date']} "
                  f"{j.get('company', '?')} | {str(j.get('title', '?'))[:40]}"
                  + (f" | {v['note']}" if v.get("note") else ""))

    elif args.cmd == "stats":
        counts = {s: 0 for s in STATUSES[1:]}
        for v in tracker.values():
            counts[v["status"]] = counts.get(v["status"], 0) + 1
        total = len(tracker)
        print(f"投递总数: {total}")
        for s, c in counts.items():
            if c:
                print(f"  {s}: {c}（{c / total * 100:.0f}%）")


if __name__ == "__main__":
    main()
