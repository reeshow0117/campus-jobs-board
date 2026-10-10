#!/usr/bin/env python3
"""轻量评测：对规则打分器跑断言集，验证排序行为符合预期

覆盖：正常（目标岗位高分）、边界（过期淘汰、零分过滤、缺字段容错）、
对抗（负面词降权、无关岗位不得进入 Top）。

用法: python3 agent/selfcheck.py  （全部通过退出码 0，否则 1）
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matcher import load_config, score_job, rank_jobs

TODAY = date(2026, 10, 8)
FUTURE = (TODAY + timedelta(days=30)).isoformat()
SOON = (TODAY + timedelta(days=3)).isoformat()
PAST = (TODAY - timedelta(days=1)).isoformat()

CASES = [
    # (用例名, 岗位, 断言函数: (score, reasons, expired) -> bool)
    ("AI产品经理岗应高分",
     {"id": 1, "company": "腾讯", "title": "AI产品经理", "city_tags": ["深圳"],
      "industry": "IT/互联网/游戏/电商", "ref_code": "ABC123", "deadline": FUTURE},
     lambda s, r, e: s >= 40 and not e),
    ("深圳首选城市加分",
     {"id": 2, "company": "A", "title": "产品经理", "city_tags": ["深圳"], "deadline": FUTURE},
     lambda s, r, e: any("首选城市" in x for x in r)),
    ("非目标城市不加分",
     {"id": 3, "company": "A", "title": "产品经理", "city_tags": ["兰州"], "deadline": FUTURE},
     lambda s, r, e: not any("城市" in x for x in r)),
    ("销售岗降权",
     {"id": 4, "company": "A", "title": "销售经理", "city_tags": ["深圳"], "deadline": FUTURE},
     lambda s, r, e: any("方向排除" in x for x in r)),
    ("过期岗位被淘汰",
     {"id": 5, "company": "腾讯", "title": "AI产品经理", "city_tags": ["深圳"],
      "deadline": PAST},
     lambda s, r, e: e is True),
    ("7天内截止加分",
     {"id": 6, "company": "A", "title": "产品经理", "city_tags": ["深圳"], "deadline": SOON},
     lambda s, r, e: any("截止" in x for x in r)),
    ("有内推码加分",
     {"id": 7, "company": "A", "title": "产品经理", "city_tags": ["深圳"],
      "ref_code": "XYZ", "deadline": FUTURE},
     lambda s, r, e: any("内推码" in x for x in r)),
    ("缺字段不崩溃",
     {"id": 8, "company": "A"},
     lambda s, r, e: isinstance(s, int)),
    ("非法日期按无截止处理",
     {"id": 9, "company": "A", "title": "产品经理", "city_tags": ["深圳"],
      "deadline": "尽快投递", "deadline_text": "尽快"},
     lambda s, r, e: not e),
    ("房地产行业降权",
     {"id": 10, "company": "A", "title": "产品经理", "city_tags": ["深圳"],
      "industry": "房地产/建筑/物业", "deadline": FUTURE},
     lambda s, r, e: any("房地产" in x for x in r)),
]


def main():
    cfg = load_config()
    passed, failed = 0, []
    for name, job, check in CASES:
        s, r, e = score_job(job, cfg, TODAY)
        if check(s, r, e):
            passed += 1
            print(f"  PASS {name} (score={s})")
        else:
            failed.append(name)
            print(f"  FAIL {name} (score={s}, reasons={r}, expired={e})")

    # 排序级断言：目标岗位必须排在无关岗位前
    jobs = [
        {"id": 100, "company": "腾讯", "title": "AI产品经理", "city_tags": ["深圳"],
         "industry": "IT/互联网/游戏/电商", "ref_code": "ABC", "deadline": FUTURE},
        {"id": 101, "company": "X", "title": "电话客服", "city_tags": ["兰州"],
         "deadline": FUTURE},
        {"id": 102, "company": "Y", "title": "AI产品经理", "city_tags": ["深圳"],
         "deadline": PAST},
    ]
    ranked = rank_jobs(jobs, cfg, TODAY)
    ids = [j["id"] for j, _, _ in ranked]
    if ids == [100]:
        passed += 1
        print("  PASS 排序正确且过期/零分岗位被过滤")
    else:
        failed.append("排序断言")
        print(f"  FAIL 排序结果异常: {ids}")

    print(f"\n{passed}/{len(CASES) + 1} 通过")

    # 简历防编造自检断言
    from resume_gen import verify_resume, load_materials
    materials = {
        "S1": {"org": "腾讯", "role": "实习生", "period": "2026", "body": "- 做了A\n"},
        "P1": {"org": "某项目", "role": "作者", "period": "2025", "body": "- 做了B\n"},
    }
    total_extra = 3
    # 正常：引用存在且组织名一致
    good = "## 实习\n### S1 | 腾讯 | 实习生 | 2026\n- 做了A [@S1]\n"
    if verify_resume(good, materials) == []:
        passed += 1
        print("  PASS 简历自检：合法稿通过")
    else:
        failed.append("简历自检-合法稿")
        print("  FAIL 合法简历被误报")
    # 对抗：引用不存在的编号
    ghost = "### S1 | 腾讯 | 实习生 | 2026\n- 做了X [@S9]\n"
    if any("S9" in v for v in verify_resume(ghost, materials)):
        passed += 1
        print("  PASS 简历自检：虚构编号被拦截")
    else:
        failed.append("简历自检-虚构编号")
        print("  FAIL 虚构编号未被发现")
    # 对抗：组织名被篡改
    tampered = "### S1 | 阿里巴巴 | 实习生 | 2026\n- 做了A [@S1]\n"
    if any("篡改" in v for v in verify_resume(tampered, materials)):
        passed += 1
        print("  PASS 简历自检：组织名篡改被拦截")
    else:
        failed.append("简历自检-组织名篡改")
        print("  FAIL 组织名篡改未被发现")

    print(f"简历自检 {passed - len(CASES) - 1}/{total_extra} 通过")
    if failed:
        print("未通过:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
