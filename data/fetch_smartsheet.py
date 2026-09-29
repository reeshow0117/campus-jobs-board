#!/usr/bin/env python3
"""抓取腾讯文档智能表格(sheet1: 27届校招秋招实习内推表)全部子表并解析为统一 JSON"""
import json, re, base64, zlib, subprocess, sys, os

DOC_ID = "DWnBUVm9OVFhuSEJ4"
PAD_ID = "300000000$ZpTVoNTXnHBx"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

TABS = [
    ("twLpD9", "秋招内推表"),
    ("tXNsDk", "每日更新"),
    ("tFd3IQ", "互联网类秋招"),
    ("tjVbba", "科技类秋招"),
    ("t6vu8W", "游戏类秋招"),
    ("tEJPf5", "金融&教育类秋招"),
    ("tmBAC4", "实习内推表"),
    ("tt6wOk", "国央企求职资料库"),
    ("tziPRy", "官方招聘平台汇总"),
    ("taWqVu", "华为部门直推"),
]

def curl(url):
    r = subprocess.run(["curl", "-s", url, "-H", f"User-Agent: {UA}",
                        "-H", f"Referer: https://docs.qq.com/smartsheet/{DOC_ID}"],
                       capture_output=True, text=True)
    return r.stdout

def decode_blob(blob):
    blob += "=" * (-len(blob) % 4)
    return json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))

def find_row_container(o):
    """递归找包含 rXXXXXX 行id 的字典"""
    best = None
    def walk(node):
        nonlocal best
        if isinstance(node, dict):
            rowkeys = [k for k in node if re.fullmatch(r"r[A-Za-z0-9]{5}", k)]
            if len(rowkeys) >= 3 and (best is None or len(rowkeys) > len(best[1])):
                best = (node, rowkeys)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(o)
    return best[0] if best else None

def find_fields(o):
    """递归找字段定义: dict of {fXXXXXX: {k30: name, k31: type, ...}}"""
    res = {}
    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if (re.fullmatch(r"f[A-Za-z0-9]{5}", k) and isinstance(v, dict)
                        and isinstance(v.get("k30"), str) and isinstance(v.get("k31"), int)):
                    res[k] = v
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(o)
    return res

def field_options(f):
    """提取选项映射 {optId: label}"""
    opts = {}
    for key in ("k9", "k17"):
        grp = f.get(key)
        if isinstance(grp, dict):
            for item in grp.get("k3", []):
                if isinstance(item, dict) and "k1" in item and "k2" in item:
                    opts[item["k1"]] = item["k2"]
    return opts

def cell_text(cell, ftype, opts):
    if not isinstance(cell, dict):
        return ""
    if ftype == 9:  # select
        ids = cell.get("k9", [])
        return "、".join(opts.get(i, i) for i in ids)
    if ftype == 17:  # 多选/标签
        ids = cell.get("k17", [])
        return "、".join(opts.get(i, i) for i in ids)
    if ftype == 8:  # link
        links = cell.get("k8", [])
        parts = []
        for l in links:
            txt = (l.get("k2") or "").strip()
            url = (l.get("k3") or "").strip()
            if url.startswith("http") and url != txt:
                parts.append(f"{txt} {url}".strip())
            else:
                parts.append(txt or url)
        return " ".join(p for p in parts if p)
    if ftype == 23:  # person
        return "、".join(p.get("k2", "") for p in cell.get("k23", []))
    # default text: k1 list of segments（url 段优先取链接）
    segs = cell.get("k1")
    if isinstance(segs, list):
        out = []
        for s in segs:
            if isinstance(s, dict):
                url = (s.get("k3") or "").strip()
                if s.get("k1") == "url" and url.startswith("http"):
                    out.append(url)
                else:
                    out.append(s.get("k2", ""))
            elif isinstance(s, str):
                out.append(s)
        return "".join(out)
    if isinstance(segs, str):
        return segs
    return ""

def parse_tab(tab_id, tab_name):
    # 1) opendoc 拿字段定义（含选项）
    odoc_url = (f"https://docs.qq.com/dop-api/opendoc?tab={tab_id}&u=&noEscape=1"
                f"&enableSmartsheetSplit=1&supportOptimizedVer=4&chunkCellSize=15000"
                f"&enableChunkRank=1&startrow=0&endrow=5&id={DOC_ID}&normal=1"
                f"&outformat=1&wb=1&nowb=0&callback=clientVarsCallback")
    raw0 = curl(odoc_url)
    m = re.match(r"clientVarsCallback\((.*)\)\s*$", raw0, re.S)
    fields = {}
    if m:
        try:
            od = json.loads(m.group(1))
            txt = od["clientVars"]["collab_client_vars"]["initialAttributedText"]["text"]
            if txt and "smartsheet" in txt[0]:
                dec0 = decode_blob(txt[0]["smartsheet"])
                fields = find_fields(dec0)
        except Exception as e:
            print(f"[{tab_name}] opendoc fields error: {e}")
    # 2) get/sheet 拿行数据
    url = (f"https://docs.qq.com/dop-api/get/sheet?padId={PAD_ID.replace('$','%24')}"
           f"&subId={tab_id}&startrow=0&endrow=5000&outformat=1&normal=1&nowb=1"
           f"&needSheetState=2&optimizedVer=2&enableChunkRank=0")
    raw = curl(url)
    try:
        data = json.loads(raw)
    except Exception:
        print(f"[{tab_name}] JSON parse fail, head: {raw[:200]}")
        return []
    if data.get("retcode") != 0:
        print(f"[{tab_name}] retcode={data.get('retcode')} msg={data.get('msg')}")
        return []
    texts = data["data"]["initialAttributedText"]["text"]
    if not texts or "smartsheet" not in texts[0]:
        print(f"[{tab_name}] no smartsheet blob")
        return []
    dec = decode_blob(texts[0]["smartsheet"])
    if not fields:
        fields = find_fields(dec)
    opts_map = {fid: field_options(f) for fid, f in fields.items()}
    rows_obj = find_row_container(dec)
    if not rows_obj:
        print(f"[{tab_name}] no rows found")
        return []
    rows = []
    for rid, rval in rows_obj.items():
        if not isinstance(rval, dict):
            continue
        cells = rval.get("k1", {})
        rec = {"_rid": rid, "_tab": tab_name}
        for fid, cell in cells.items():
            f = fields.get(fid)
            if not f:
                continue
            name = f.get("k30", fid)
            ftype = f.get("k31", 1)
            rec[name] = cell_text(cell, ftype, opts_map.get(fid, {}))
        rows.append(rec)
    print(f"[{tab_name}] fields={len(fields)} rows={len(rows)}")
    return rows

def main():
    all_rows = []
    for tab_id, tab_name in TABS:
        try:
            rows = parse_tab(tab_id, tab_name)
            all_rows.extend(rows)
        except Exception as e:
            print(f"[{tab_name}] ERROR: {e}")
    out = os.path.join(OUT_DIR, "sheet1_jobs.json")
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(all_rows, fp, ensure_ascii=False, indent=1)
    print(f"TOTAL {len(all_rows)} rows -> {out}")

if __name__ == "__main__":
    main()
