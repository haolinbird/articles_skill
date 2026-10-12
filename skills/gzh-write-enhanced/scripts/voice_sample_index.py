#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voice_sample_index.py — 真人历史语料自动识别与口吻校准索引

用途
----
把「你本人以前写过的文章」当作活人感标杆。写作前跑一次本脚本：
  - 自动定位项目根的 wechat_exports/ 目录（无需手填路径）
  - 识别其中所有 *.md 真人文章（排除 README.md 与隐藏文件）
  - 抽取每篇的标题 / 字数 / 开头段落（口吻样本）/ 转场词命中 / 代表性第一人称句
  - 若给定 --topic，按中文字二元文法重叠度排序，推荐最相关的 top N 篇

退出码
------
  0  正常（无论有无样本，都不中断流水线）
  2  参数或目录探测异常（不常见）

无样本时打印 NO_SAMPLES，流水线退回 author_voice.md 单基准；有样本时打印
RECOMMENDED 路径列表，AI 写作前应 Read 这些文件全文校准自然语感。

用法
----
  python3 voice_sample_index.py [--root <项目根>] [--topic "选题关键词"] [--top N] [--json]
"""

import argparse
import json
import os
import re
import sys

# 已知的口语化转场词（用于统计真人文章里实际用了哪些，供校准参考）
TRANSITIONS = [
    "说实话", "说真的", "其实吧", "好家伙", "我跟你说", "你别笑", "坦白讲",
    "不瞒你说", "再说了", "说白了", "讲真", "说句实话", "说实在的", "话说回来",
    "不过说真的", "讲道理", "你发现没", "你品", "你细品", "咱就说",
]

CJK = re.compile(r"[一-鿿]")
SENT_SPLIT = re.compile(r"[。！？!?\n]")


def find_root(start):
    """从 start 向上找含 skills/ 与 config/ 的目录作为项目根。"""
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, "skills")) and os.path.isdir(os.path.join(cur, "config")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def count_cjk(text):
    return len(CJK.findall(text))


def extract_title(text):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return "(无标题)"


def first_paragraph(text, limit=220):
    """取标题之后的第一个非空段落作为开头口吻样本。"""
    lines = [l.strip() for l in text.splitlines()]
    # 跳过顶部的标题行 / HTML 注释 / 引用元数据 / 空行 / 首图 / 分隔线，落到第一段文字正文
    idx = 0
    while idx < len(lines) and (
        lines[idx].startswith("#")
        or lines[idx].startswith("<!--")
        or lines[idx].startswith(">")
        or lines[idx].startswith("!")
        or lines[idx] in ("---", "***", "___", "|")
        or not lines[idx]
    ):
        idx += 1
    para = []
    while idx < len(lines):
        ln = lines[idx].strip()
        if not ln:
            if para:
                break
            idx += 1
            continue
        para.append(ln)
        idx += 1
        if sum(len(p) for p in para) > limit:
            break
    out = " ".join(para)
    return out[:limit] + ("…" if len(out) > limit else "")


def signature_sentences(text, limit=4, max_len=46):
    """抽取含第一人称的代表性短句，体现真人语气纹理。"""
    sents = [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]
    picked = []
    for s in sents:
        if "我" in s and 12 <= len(s) <= max_len:
            picked.append(s)
        if len(picked) >= limit:
            break
    return picked


def bigrams(text):
    """中文字二元文法集合，用于相关度近似。"""
    chars = "".join(CJK.findall(text))
    if len(chars) < 2:
        return set(chars)
    return set(chars[i:i + 2] for i in range(len(chars) - 1))


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def main():
    ap = argparse.ArgumentParser(description="真人历史语料自动识别与口吻校准索引")
    ap.add_argument("--root", default=None, help="项目根目录（缺省自动探测）")
    ap.add_argument("--topic", default=None, help="当前选题关键词，用于相关度排序推荐")
    ap.add_argument("--top", type=int, default=3, help="推荐读取的最大篇数（默认 3）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结构化索引")
    args = ap.parse_args()

    root = args.root or find_root(os.path.dirname(os.path.abspath(__file__)))
    if not root:
        msg = "NO_ROOT: 无法定位项目根（需含 skills/ 与 config/），退回 author_voice.md 单基准"
        if args.json:
            print(json.dumps({"status": "no_root", "samples": []}, ensure_ascii=False))
        else:
            print(msg)
        return 0

    export_dir = os.path.join(root, "wechat_exports")
    if not os.path.isdir(export_dir):
        msg = "NO_SAMPLES: wechat_exports/ 不存在，退回 author_voice.md 单基准（写作前无需额外操作）"
        if args.json:
            print(json.dumps({"status": "no_samples", "root": root, "samples": []}, ensure_ascii=False))
        else:
            print(msg)
        return 0

    files = []
    for fn in sorted(os.listdir(export_dir)):
        if not fn.endswith(".md"):
            continue
        if fn == "README.md" or fn.startswith("."):
            continue
        files.append(os.path.join(export_dir, fn))

    if not files:
        msg = "NO_SAMPLES: wechat_exports/ 暂无文章（仅 README 或为空），退回 author_voice.md 单基准"
        if args.json:
            print(json.dumps({"status": "no_samples", "root": root, "samples": []}, ensure_ascii=False))
        else:
            print(msg)
        return 0

    samples = []
    for fp in files:
        try:
            text = open(fp, encoding="utf-8").read()
        except Exception as e:
            samples.append({"path": fp, "error": str(e)})
            continue
        title = extract_title(text)
        wc = count_cjk(text)
        opening = first_paragraph(text)
        trans = [t for t in TRANSITIONS if t in text]
        sig = signature_sentences(text)
        samples.append({
            "path": fp,
            "title": title,
            "word_count": wc,
            "opening": opening,
            "transitions": trans,
            "signature_sentences": sig,
            "_text": text,  # 仅用于内存相关度计算，不输出
        })

    # 相关度推荐
    recommended = []
    if args.topic:
        topic_bg = bigrams(args.topic)
        ranked = []
        for s in samples:
            if "_text" not in s:
                continue
            score = jaccard(topic_bg, bigrams(s["_text"]))
            ranked.append((score, s))
        ranked.sort(key=lambda x: x[0], reverse=True)
        recommended = [s["path"] for _, s in ranked[:args.top]]
    else:
        recommended = [s["path"] for s in samples[:args.top]]

    status = "ok"
    if args.json:
        out = {
            "status": status,
            "root": root,
            "count": len(samples),
            "samples": [
                {k: v for k, v in s.items() if k != "_text"} for s in samples
            ],
            "recommended": recommended,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"FOUND {len(samples)} 篇真人历史文章（位于 {export_dir}）")
        print("=" * 72)
        for i, s in enumerate(samples, 1):
            if "error" in s:
                print(f"{i}. [读取失败] {os.path.basename(s['path'])}: {s['error']}")
                continue
            print(f"{i}. 《{s['title']}》  字数≈{s['word_count']}  {os.path.basename(s['path'])}")
            print(f"   开头：{s['opening']}")
            if s["transitions"]:
                print(f"   常用转场：{' / '.join(s['transitions'][:8])}")
            if s["signature_sentences"]:
                print(f"   口吻句：{' ｜ '.join(s['signature_sentences'][:3])}")
            print()
        if args.topic:
            print(f"按选题「{args.topic}」相关度，推荐先读这 {len(recommended)} 篇全文校准口吻：")
        else:
            print(f"未给定选题，默认推荐先读前 {len(recommended)} 篇全文校准口吻：")
        for p in recommended:
            print(f"  - {p}")
        print()
        print("RECOMMENDED 已列出；写作前 Read 这些文件，对齐真人语感后再动笔。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
