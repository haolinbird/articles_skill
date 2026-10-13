#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S4b 前置：从终稿抽取「可发布的干净正文」，供 gzh_format.cjs 排版。

为什么需要这个脚本：
  终稿（articles/YYYYMMDD[/pN]/final.md）里混着三类不能发的内容，手工截取极易漏：
    1. 开头的「## 备选标题（40 个）」标题区（40 条标题，排进正文等于事故）
    2. 结尾的「## 本篇自检」自检表
    3. 「## 待人工确认」等内部段落
  手工按「h1 到本篇自检之前」截取，会把标题区整段带进去（2026-10-12 实测踩过）。

抽取规则：
  [h1 主标题] + [备选标题区之后 → 第一个终止标题之前]（保留「素材来源与出处」表）

⚠️ 关键防呆：定位标题前必须先剥离代码块。正文代码块里常有 `# target.py`
   这类以 # 开头的注释行，直接按 ^# 匹配会把代码行误判成标题。

用法：
  python3 extract_clean.py articles/20261012/final.md
  python3 extract_clean.py articles/20261011/p1_final.md -o articles/20261011/p1_clean.md
  python3 extract_clean.py <final.md> --stop-heading "## 本篇自检" --check-only

退出码：0 成功；1 自检未通过（已写文件也会被保留，便于人工排查）；2 输入异常
"""

import argparse
import os
import re
import sys

DEFAULT_STOP_HEADINGS = ["## 本篇自检", "## 待人工确认"]
TITLES_HEADING = "## 备选标题"
SOURCE_HEADING = "素材来源与出处"


def strip_code_lines(lines):
    """返回掩码列表：True 表示该行处于代码块内部（含围栏行本身）。"""
    in_block = False
    mask = []
    for ln in lines:
        stripped = ln.strip()
        is_fence = stripped.startswith("```") or stripped.startswith("~~~")
        if is_fence:
            mask.append(True)
            in_block = not in_block
            continue
        mask.append(in_block)
    return mask


def find_heading(lines, mask, heading, start=0):
    """在非代码块行里找标题行（整行相等或以其开头），返回索引，找不到返回 -1。"""
    for i in range(start, len(lines)):
        if mask[i]:
            continue
        s = lines[i].rstrip()
        if s == heading or s.startswith(heading):
            return i
    return -1


def find_h1(lines, mask):
    for i, ln in enumerate(lines):
        if mask[i]:
            continue
        if re.match(r"^# (?!#)", ln.rstrip()):
            return i
    return -1


def extract(text, stop_headings=None, titles_heading=TITLES_HEADING):
    stop_headings = stop_headings or DEFAULT_STOP_HEADINGS
    lines = text.split("\n")
    mask = strip_code_lines(lines)

    h1 = find_h1(lines, mask)
    if h1 < 0:
        raise ValueError("未找到主标题 h1（^# 且非 ##），无法抽取")

    # 终止点：所有终止标题中最靠前的那个
    stops = [i for i in (find_heading(lines, mask, h, h1 + 1) for h in stop_headings) if i >= 0]
    end = min(stops) if stops else len(lines)

    # 备选标题区：若存在，正文从其后第一条独立分隔线之后开始；否则紧接 h1
    t_i = find_heading(lines, mask, titles_heading, h1 + 1)
    body_start = h1 + 1
    note = "未发现备选标题区，正文紧接主标题"
    if 0 <= t_i < end:
        sep = next((j for j in range(t_i + 1, end)
                    if not mask[j] and lines[j].strip() == "---"), -1)
        if sep >= 0:
            body_start = sep + 1
            note = f"已跳过备选标题区（第 {t_i + 1}-{sep + 1} 行）"
        else:
            note = f"发现备选标题区但无 --- 分隔线，退化为整段跳过（第 {t_i + 1} 行起）"
            body_start = end  # 保守：宁可少排也不排进标题

    clean = lines[h1] + "\n\n" + "\n".join(lines[body_start:end]).strip() + "\n"
    return clean, {
        "note": note,
        "end_reason": f"终止于 {lines[end].strip()}" if stops else "未发现终止标题，取到文件末",
    }


def selfcheck(clean, expect_images=None):
    issues = []
    if TITLES_HEADING.lstrip("# ").split("（")[0] in clean or "备选标题" in clean:
        issues.append("残留备选标题区")
    for h in DEFAULT_STOP_HEADINGS:
        if h.lstrip("# ") in clean:
            issues.append(f"残留 {h}")
    if SOURCE_HEADING not in clean:
        issues.append("缺失「素材来源与出处」表（链接是内容可信度底线，不该丢）")
    n_img = clean.count("![")
    if expect_images is not None and n_img != expect_images:
        issues.append(f"图片引用 {n_img} 处，预期 {expect_images} 处")
    if not clean.lstrip().startswith("# "):
        issues.append("首行不是主标题 h1")
    return issues, n_img


def main():
    ap = argparse.ArgumentParser(description="从终稿抽取干净正文（S4b 排版输入）")
    ap.add_argument("final_md", help="终稿 md 路径")
    ap.add_argument("-o", "--out", help="输出路径，默认与输入同目录的 _clean.md")
    ap.add_argument("--stop-heading", action="append", default=None,
                    help="终止标题，可重复；默认 ## 本篇自检 / ## 待人工确认")
    ap.add_argument("--expect-images", type=int, default=None,
                    help="预期图片引用数（与 S4 张数对齐）")
    ap.add_argument("--check-only", action="store_true", help="只自检不写文件")
    args = ap.parse_args()

    src = args.final_md
    if not os.path.isfile(src):
        print(f"❌ 输入不存在：{src}")
        return 2

    text = open(src, encoding="utf-8").read()
    try:
        clean, info = extract(text, args.stop_heading)
    except ValueError as e:
        print(f"❌ {e}")
        return 2

    issues, n_img = selfcheck(clean, args.expect_images)

    if args.out:
        out = args.out
    elif src.endswith("final.md"):
        # 新结构 articles/YYYYMMDD/final.md -> clean.md
        out = src[: -len("final.md")] + "clean.md"
    elif "_final.md" in src:
        # 兼容旧结构 articles/YYYYMMDD_final.md -> YYYYMMDD_clean.md
        out = src.replace("_final.md", "_clean.md")
    else:
        # 兜底：避免覆盖输入，派生 _clean 文件名
        base, ext = os.path.splitext(src)
        out = base + "_clean" + ext
    if out == src:
        print(f"❌ 输出路径与输入相同，拒绝覆盖：{out}")
        return 2

    if not args.check_only:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        open(out, "w", encoding="utf-8").write(clean)

    print(f"输入 {src}")
    print(f"输出 {out if not args.check_only else '(check-only，未写文件)'}")
    print(f"  {info['note']}")
    print(f"  {info['end_reason']}")
    print(f"  字符数 {len(clean)}｜图片引用 {n_img} 处")
    print(f"  首行：{clean.split(chr(10))[0][:50]}")

    if issues:
        print("\n❌ 自检未通过：")
        for i in issues:
            print(f"   - {i}")
        return 1
    print("\n✅ 自检通过：无标题区/自检区残留，来源表完整，首行为主标题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
