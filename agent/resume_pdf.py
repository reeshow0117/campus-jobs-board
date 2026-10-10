#!/usr/bin/env python3
"""把定制简历 Markdown 渲染成 PDF，以用户认可的单页简历版式为基准输出

版式规格（从原 PDF 实测）：
  - 页眉：姓名居中粗体 + 联系方式居中一行；右上角证件照（约 2.0×2.9cm，贴近页缘）
  - 板块标题：中文（ENGLISH CAPS）粗体 + 细分隔线，首板块分隔线避开照片
  - 条目：「组织 ｜ 角色」粗体一行 + 日期粗体右对齐；教育条目角色另起一行斜体
  - 要点：可移植的矢量 ➢ 引导，主题词加粗（**主题词：**内容）
  - 正文宋体 10pt，单页 A4，溢出自动缩排（100% → 92% → 85% → 78%）

字体：优先宋体（macOS Songti.ttc / Linux Noto Serif CJK）。可用
QIUZHAO_RESUME_FONT / QIUZHAO_RESUME_FONT_BOLD 指定 ttf|ttc 路径。
照片：QIUZHAO_RESUME_PHOTO 或 agent/profiles/<user>/photo.png。

依赖：reportlab>=4.2、pypdf>=4.0（单页校验为强制约束）
"""
import html
import os
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Table, TableStyle,
)

# (regular_path, regular_idx, bold_path, bold_idx)
FONT_SETS = [
    # macOS 宋体-简（最接近 SimSun）
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 6,
     "/System/Library/Fonts/Supplemental/Songti.ttc", 1),
    # Linux: fonts-noto-cjk-extra 的宋体风格衬线体
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", 2,
     "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", 2),
    # 部分发行版只包含 Regular 合集，仍用衬线体；加粗由 ReportLab 合成。
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", 2, None, 0),
]

SECTION_MAP = {
    "求职亮点": "求职亮点（HIGHLIGHTS）",
    "教育经历": "教育背景（EDUCATION）",
    "实习经历": "实习经历（INTERNSHIP EXPERIENCE）",
    "工作经历": "工作经历（WORK EXPERIENCES）",
    "项目经历": "项目经历（PROJECT EXPERIENCE）",
    "社会实践": "社会实践（ACTIVITIES）",
    "奖项荣誉": "奖项荣誉（HONORS & AWARDS）",
    "技能与证书": "语言与技能（LANGUAGES & SKILLS）",
}
SECTION_ORDER = ["求职亮点", "教育经历", "实习经历", "工作经历", "项目经历",
                 "社会实践", "奖项荣誉", "技能与证书"]

CITE_RE = re.compile(r"\s*\[@[A-Z]+\d+\]")
# 条目头兼容 3 段（编号|组织|时间）与 4 段（编号|组织|角色|时间）
HEAD_RE = re.compile(r"^###\s+([A-Z]+\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*(?:\|\s*([^|\n]+?)\s*)?$")
class ArrowBullet(Paragraph):
    """绘制矢量 ➢ 项目符号，不依赖或再分发原 PDF 的私有字体。"""

    def draw(self):
        super().draw()
        canvas = self.canv
        canvas.saveState()
        canvas.translate(2, self.height - self.style.leading * 0.68)
        canvas.setStrokeColorRGB(0, 0, 0)
        canvas.setLineWidth(0.8)
        shape = canvas.beginPath()
        shape.moveTo(0, 2.4)
        shape.lineTo(4, 2.4)
        shape.lineTo(4, 4.8)
        shape.lineTo(9, 0)
        shape.lineTo(4, -4.8)
        shape.lineTo(4, -2.4)
        shape.lineTo(0, -2.4)
        shape.close()
        canvas.drawPath(shape, stroke=1, fill=0)
        canvas.restoreState()


def register_fonts():
    """注册中文正文字体和粗体。"""
    env_r = os.environ.get("QIUZHAO_RESUME_FONT")
    env_b = os.environ.get("QIUZHAO_RESUME_FONT_BOLD")
    sets = ([(env_r, 0, env_b, 0)] if env_r else []) + FONT_SETS
    for reg_path, reg_idx, bold_path, bold_idx in sets:
        if not (reg_path and os.path.exists(reg_path)):
            continue
        try:
            pdfmetrics.registerFont(TTFont("CJK", reg_path, subfontIndex=reg_idx))
            bold_name = "CJK"
            if bold_path and os.path.exists(bold_path):
                try:
                    pdfmetrics.registerFont(TTFont("CJK-Bold", bold_path, subfontIndex=bold_idx))
                    bold_name = "CJK-Bold"
                except Exception:
                    pass
            pdfmetrics.registerFontFamily("CJK", normal="CJK", bold=bold_name,
                                          italic="CJK", boldItalic=bold_name)
            return True
        except Exception:
            continue
    raise RuntimeError(
        "找不到宋体/衬线中文字体。Linux 请安装 fonts-noto-cjk-extra，"
        "或设 QIUZHAO_RESUME_FONT / QIUZHAO_RESUME_FONT_BOLD 指定衬线字体路径")


def strip_cites(text):
    return CITE_RE.sub("", text).strip()


def md_inline(text):
    """先转义用户文本，再转换有限的 Markdown 加粗标签。"""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text))


def parse_resume_md(md):
    """解析生成的简历 Markdown 为结构化数据。"""
    lines = md.split("\n")
    doc = {"name": "", "contact": "", "sections": []}
    cur_sec, cur_entry = None, None
    for i, line in enumerate(lines):
        line = line.rstrip()
        if line.startswith("# ") and not doc["name"]:
            title = line[2:].strip()
            if " - " in title:
                doc["name"], intent = title.split(" - ", 1)
            else:
                doc["name"], intent = title, ""
            for j in range(i + 1, min(i + 4, len(lines))):
                t = lines[j].strip()
                if t and not t.startswith("#"):
                    doc["contact"] = strip_cites(t)
                    break
            if intent:
                doc["contact"] = (doc["contact"] + " ｜ " + intent).strip(" ｜")
            continue
        m2 = re.match(r"^##\s+(.+)$", line)
        if m2:
            title = m2.group(1).strip()
            key = next((k for k in SECTION_ORDER if k in title), title)
            cur_sec = {"key": key, "entries": [], "bullets": []}
            doc["sections"].append(cur_sec)
            cur_entry = None
            continue
        if cur_sec is None:
            continue
        m3 = HEAD_RE.match(line)
        if m3:
            eid, org, role, period = m3.groups()
            if period is None and re.match(r"^[\d年月日./ -]+", role or ""):
                role, period = "", role  # 3 段写法时第二段是时间
            cur_entry = {"id": eid, "org": org, "role": role or "",
                         "period": period or "", "bullets": []}
            cur_sec["entries"].append(cur_entry)
            continue
        if line.startswith(("- ", "* ")):
            b = strip_cites(line[2:])
            if not b:
                continue
            (cur_entry["bullets"] if cur_entry is not None
             else cur_sec["bullets"]).append(b)
    doc["sections"].sort(key=lambda s: SECTION_ORDER.index(s["key"])
                         if s["key"] in SECTION_ORDER else 99)
    return doc


def _photo_callback(photo_path, draw):
    """onPage 回调：首页右上角画证件照（贴近页缘，与原简历一致）。"""
    def _cb(canvas, _doc):
        if draw and photo_path and os.path.exists(photo_path):
            # 照片保持原始比例，放在页眉右侧；底边须高于首个板块分隔线。
            # 原先 2.0×2.86cm、距顶 0.6cm 会与“求职亮点”横线及首条正文重叠。
            w, h = 1.8 * cm, 2.55 * cm
            pw, ph = A4
            canvas.saveState()
            canvas.drawImage(photo_path, pw - 1.2 * cm - w, ph - 0.2 * cm - h,
                             width=w, height=h, preserveAspectRatio=True, mask="auto")
            canvas.restoreState()
    return _cb


def render_pdf(doc, out_path, scale=1.0, photo_path=None):
    """渲染为 A4 PDF。scale 用于内容溢出时整体缩排。"""
    def st(name, **kw):
        base = dict(fontName="CJK", fontSize=10 * scale, leading=13.6 * scale,
                    textColor="#000000")
        base.update(kw)
        return ParagraphStyle(name, **base)

    st_name = st("name", fontSize=14 * scale, leading=17 * scale, alignment=1)
    st_contact = st("contact", fontSize=9 * scale, leading=12 * scale,
                    alignment=1, textColor="#222222")
    st_sec = st("sec", fontSize=11 * scale, leading=14 * scale,
                spaceBefore=9 * scale, spaceAfter=1)
    st_bullet = st("bullet", fontSize=10 * scale, leading=14.2 * scale,
                   leftIndent=15 * scale, firstLineIndent=0, spaceBefore=2.6 * scale)
    st_org = st("org")
    st_role = st("role", fontSize=9.5 * scale, leading=13 * scale)
    st_date = st("date", alignment=2)

    story = [Paragraph(f"<b>{html.escape(doc['name'])}</b>", st_name)]
    if doc["contact"]:
        story.append(Paragraph(html.escape(doc["contact"]), st_contact))

    for index, sec in enumerate(doc["sections"]):
        title = SECTION_MAP.get(sec["key"], sec["key"])
        story.append(Paragraph(f"<b>{html.escape(title)}</b>", st_sec))
        # 首个板块靠近右上角照片，分隔线不要延伸到照片的水平范围。
        story.append(HRFlowable(width="86%" if index == 0 and photo_path else "100%",
                                hAlign="LEFT", thickness=0.8,
                                spaceBefore=0, spaceAfter=4 * scale))
        for b in sec["bullets"]:
            story.append(ArrowBullet(md_inline(b), st_bullet))
        for e in sec["entries"]:
            # 第一行：组织 ｜ 角色（粗体）……日期（右对齐）；教育条目角色另起斜体行
            head = f"<b>{md_inline(e['org'])}</b>"
            role_inline = e["role"] and not e["id"].startswith("E")
            if role_inline:
                head += f"<b> ｜ {md_inline(e['role'])}</b>"
            t = Table([[Paragraph(head, st_org),
                        Paragraph(f"<b>{html.escape(e['period'])}</b>", st_date)]],
                      colWidths=[13.4 * cm, 4.4 * cm])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5 * scale),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(t)
            if e["role"] and not role_inline:
                story.append(Paragraph(f"<i>{md_inline(e['role'])}</i>", st_role))
            for b in e["bullets"]:
                story.append(ArrowBullet(md_inline(b), st_bullet))

    pdf = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=1.6 * cm, rightMargin=1.6 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        title=doc["name"],
    )
    pdf.build(story,
              onFirstPage=_photo_callback(photo_path, True),
              onLaterPages=_photo_callback(photo_path, False))


def _page_count(path):
    """页数是交付硬约束；缺少检测依赖时不能假装只有一页。"""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("缺少 pypdf，无法校验简历是否为单页 PDF") from exc
    return len(PdfReader(path).pages)


def md_to_pdf(md, out_path, photo_path=None):
    """主入口：Markdown 简历 -> 单页 A4 PDF。溢出时自动缩排（最多两档）。"""
    register_fonts()
    doc = parse_resume_md(md)
    if not doc["name"]:
        raise ValueError("Markdown 中找不到 '# 姓名' 标题行")
    for scale in (1.0, 0.92, 0.85, 0.78):
        render_pdf(doc, out_path, scale=scale, photo_path=photo_path)
        if _page_count(out_path) <= 1:
            if scale < 1.0:
                print(f"  内容较长，已自动缩排至 {scale:.0%}")
            break
    else:
        os.unlink(out_path)
        raise ValueError("内容超过一页 A4；请精简要点后重新生成，不能交付多页 PDF")
    return out_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python3 agent/resume_pdf.py <简历.md> <输出.pdf> [照片路径]")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        photo = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("QIUZHAO_RESUME_PHOTO")
        md_to_pdf(f.read(), sys.argv[2], photo_path=photo)
    print(f"PDF 已生成: {sys.argv[2]}")
