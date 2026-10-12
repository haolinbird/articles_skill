#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识星球纯文本转换器（md_to_plain.py）

用途：知识星球客户端不渲染 Markdown，发布前必须把 .md 转成纯文本。
规则（与 SKILL.md 一致，严禁压缩内容，只去标记）：
  - 去掉 ** 加粗标记（保留文字）
  - 去掉 --- 分隔线，用空行替代
  - 去掉 ![](图片路径) 引用（图片通过 --files 随帖发布）
  - 去掉 > 引用前缀
  - 把 #/##/### 标题转成【】标记
  - 表格原样保留为文本（星球不渲染表格，保留可读性）
  - 代码块保留（星球纯文本下代码块是最稳的呈现方式）
用法：
  python3 md_to_plain.py <输入.md> [输出.txt]
  不传输出文件时，默认写为同名的 _纯文本.txt
"""

import os
import re
import sys


def convert(md_text: str) -> str:
    lines = md_text.split("\n")
    out = []
    in_code = False

    for raw in lines:
        line = raw.rstrip()

        # 代码块边界（保留 ``` 原样，星球纯文本下靠它辨认代码段）
        if line.lstrip().startswith("```"):
            out.append(line)
            in_code = not in_code
            continue

        # 代码块内部：原样保留，不做任何清洗
        if in_code:
            out.append(raw)
            continue

        # 分隔线 -> 空行
        if re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", line):
            out.append("")
            continue

        # 图片引用：整行只有图片则删除整行；否则删掉图片片段
        stripped_img = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
        if line.strip() and not stripped_img.strip():
            out.append("")
            continue
        line = stripped_img

        # 标题 -> 【】
        m = re.match(r"^(\s*)(#{1,6})\s*(.*)$", line)
        if m:
            indent, _, text = m.groups()
            text = text.strip()
            if text:
                # 去掉标题里残留的加粗标记
                text = text.replace("**", "")
                out.append(f"{indent}【{text}】")
            else:
                out.append("")
            continue

        # 引用前缀
        line = re.sub(r"^\s*>\s?", "", line)

        # 列表符号保留（星球不渲染，但 - 是最接近列表的视觉）
        # 加粗标记
        line = line.replace("**", "")

        # 行内代码反引号保留（不去除，保留技术感）
        out.append(line.rstrip())

    text = "\n".join(out)

    # 连续 3 个以上空行压成 2 个（不影响内容，只收空白）
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    src = sys.argv[1]
    if len(sys.argv) >= 3:
        dst = sys.argv[2]
    else:
        base, _ = os.path.splitext(src)
        dst = base + "_纯文本.txt"

    with open(src, encoding="utf-8") as f:
        md = f.read()

    plain = convert(md)

    with open(dst, "w", encoding="utf-8") as f:
        f.write(plain)

    print(f"输入: {src}  ({len(md)} 字符)")
    print(f"输出: {dst}  ({len(plain)} 字符)")
    print(f"保留率: {len(plain) / len(md) * 100:.1f}%   (低于 90% 需人工检查是否被误删内容)")


if __name__ == "__main__":
    main()
