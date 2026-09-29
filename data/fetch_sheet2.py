#!/usr/bin/env python3
"""抓取毕业帮校招表格中的内嵌智能表格(27校招岗位智能表格 ss_cc56ni)"""
import json, re, base64, zlib, subprocess, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DOC_ID = "DTENzbmppUGd2Smxk"
PAD_ID = "300000000$LCsnjiPgvJld"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def curl(url):
    r = subprocess.run(["curl", "-s", url, "-H", f"User-Agent: {UA}",
                        "-H", f"Referer: https://docs.qq.com/sheet/{DOC_ID}"],
                       capture_output=True, text=True)
    return r.stdout

def decode_blob(blob):
    blob = blob.strip()
    if blob.startswith("[[") or blob.startswith("{"):
        d = json.loads(blob)
    else:
        blob += "=" * (-len(blob) % 4)
        d = json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))
    return normalize_keys(d)

def normalize_keys(o):
    """数字字符串键统一加 k 前缀，兼容两种序列化格式"""
    if isinstance(o, dict):
        return {("k" + k if re.fullmatch(r"\d+", k) else k): normalize_keys(v) for k, v in o.items()}
    if isinstance(o, list):
        return [normalize_keys(v) for v in o]
    return o

def find_row_container(o):
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
    res = {}
    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if (re.fullmatch(r"f[A-Za-z0-9]{5}", k) and isinstance(v, dict)
                        and isinstance(v.get("k30"), str) and isinstance(v.get("k31"), int)):
                    if k not in res:
                        res[k] = v
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(o)
    return res

def field_options(f):
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
    if ftype == 9:
        ids = cell.get("k9", [])
        return "、".join(opts.get(i, i) for i in ids)
    if ftype == 17:  # 多选/标签
        ids = cell.get("k17", [])
        return "、".join(opts.get(i, i) for i in ids)
    if ftype == 8:
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
    if ftype == 23:
        return "、".join(p.get("k2", "") for p in cell.get("k23", []))
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

def main():
    # 字段定义
    odoc_url = (f"https://docs.qq.com/dop-api/opendoc?tab=ss_cc56ni&u=&noEscape=1"
                f"&enableSmartsheetSplit=1&supportOptimizedVer=4&chunkCellSize=15000"
                f"&enableChunkRank=1&startrow=0&endrow=5&id={DOC_ID}&normal=1"
                f"&outformat=1&wb=1&nowb=0&callback=clientVarsCallback")
    raw0 = curl(odoc_url)
    m = re.match(r"clientVarsCallback\((.*)\)\s*$", raw0, re.S)
    fields = {}
    if m:
        od = json.loads(m.group(1))
        txt = od["clientVars"]["collab_client_vars"]["initialAttributedText"]["text"]
        if txt and "smartsheet" in txt[0]:
            fields = find_fields(decode_blob(txt[0]["smartsheet"]))
    print("fields:", {k: v["k30"] for k, v in fields.items()})
    opts_map = {fid: field_options(f) for fid, f in fields.items()}

    # 分块拉行
    all_rows = {}
    CHUNK = 1500
    MAXR = 12041
    for start in range(0, MAXR, CHUNK):
        end = min(start + CHUNK - 1, MAXR)
        url = (f"https://docs.qq.com/dop-api/get/sheet?padId={PAD_ID.replace('$','%24')}"
               f"&subId=ss_cc56ni&startrow={start}&endrow={end}&outformat=1&normal=1"
               f"&nowb=1&needSheetState=2&optimizedVer=2&enableChunkRank=0")
        raw = curl(url)
        try:
            data = json.loads(raw)
        except Exception:
            print(f"chunk {start}-{end} parse fail"); continue
        if data.get("retcode") != 0:
            print(f"chunk {start}-{end} retcode={data.get('retcode')}"); continue
        texts = data["data"]["initialAttributedText"]["text"]
        if not texts or "smartsheet" not in texts[0]:
            print(f"chunk {start}-{end} no blob"); continue
        dec = decode_blob(texts[0]["smartsheet"])
        rows_obj = find_row_container(dec)
        if not rows_obj:
            print(f"chunk {start}-{end} no rows"); continue
        for rid, rval in rows_obj.items():
            if isinstance(rval, dict):
                all_rows[rid] = rval
        print(f"chunk {start}-{end}: cumulative {len(all_rows)}")

    rows = []
    for rid, rval in all_rows.items():
        cells = rval.get("k1", {})
        rec = {"_rid": rid, "_tab": "毕业帮岗位智能表格"}
        for fid, cell in cells.items():
            f = fields.get(fid)
            if not f:
                continue
            rec[f["k30"]] = cell_text(cell, f.get("k31", 1), opts_map.get(fid, {}))
        rows.append(rec)
    out = os.path.join(OUT_DIR, "sheet2_jobs.json")
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(rows, fp, ensure_ascii=False, indent=1)
    print(f"TOTAL {len(rows)} rows -> {out}")

if __name__ == "__main__":
    main()
