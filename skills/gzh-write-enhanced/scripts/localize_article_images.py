#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
localize_article_images.py
把 wechat_exports/ 下历史文章里的外链图片下载到本地 assets/<文章名>/ 子目录，
并把 Markdown 里的图片引用改写为相对路径，避免外链失效导致图片丢失。

用法（在流水线 S2 之前自动跑，也可手动跑）：
    python3 localize_article_images.py [--root <项目根>] [--force]

设计要点：
- 幂等：本地已存在则跳过下载；引用已是相对路径（assets/...）则跳过改写。
- 每篇文章一个独立子目录 assets/<文件名去.md>，避免不同文章图片重名冲突。
- 仅下载 http(s) 外链；data: 内联图已内嵌，不动。
- 失败不中断流水线：某张图下载失败只告警并保留原外链，exit 0。
"""

import os
import re
import sys
import json
import shutil
import urllib.request
import urllib.parse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 匹配 Markdown 图片：![alt](url) 以及可能的标题 ![alt](url "title")
MD_IMG = re.compile(r'!\[([^\]]*)\]\((\s*https?://[^)\s]+)(?:\s+"[^"]*")?\s*\)')
# 匹配 HTML <img src="...">
HTML_IMG = re.compile(r'<img\b[^>]*\bsrc=["\'](https?://[^"\']+)["\'][^>]*>', re.I)


def find_root(explicit=None):
    if explicit:
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    # 候选：scripts 上一层是技能目录，再上一层是项目根
    cand = os.path.dirname(os.path.dirname(here))
    if os.path.isdir(os.path.join(cand, "wechat_exports")):
        return cand
    # 退而找 cwd
    if os.path.isdir(os.path.join(os.getcwd(), "wechat_exports")):
        return os.getcwd()
    return cand


def slug_of(md_path):
    base = os.path.basename(md_path)
    if base.lower().endswith(".md"):
        base = base[:-3]
    return base


def ext_from_url(url):
    path = urllib.parse.urlparse(url).path
    _, ext = os.path.splitext(path)
    ext = ext.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"):
        return ext
    return ""


def referer_for(url):
    """防盗链：大部分图床校验 Referer 是否为本站来源。
    - CSDN 直链(i-blog.csdnimg.cn 等)必须用 blog.csdn.net 作 Referer，否则 403。
    - 其余图床用图片自身 origin 作 Referer，通常可过。"""
    host = urllib.parse.urlparse(url).netloc.lower()
    if "csdnimg.cn" in host or "csdn.net" in host:
        return "https://blog.csdn.net/"
    return "%s://%s/" % (urllib.parse.urlparse(url).scheme, host)


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True, "cached"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Referer": referer_for(url)}
        )
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
        if not data:
            return False, "empty"
        # 若 URL 无扩展名，按 content-type 推断
        ext = ext_from_url(url)
        if not ext:
            if "png" in ctype:
                ext = ".png"
            elif "jpeg" in ctype or "jpg" in ctype:
                ext = ".jpg"
            elif "gif" in ctype:
                ext = ".gif"
            elif "webp" in ctype:
                ext = ".webp"
            elif "svg" in ctype:
                ext = ".svg"
            else:
                ext = ".img"
        if not dest.lower().endswith(ext):
            dest += ext
        with open(dest, "wb") as f:
            f.write(data)
        return True, "%d bytes" % len(data)
    except Exception as e:  # noqa
        return False, str(e)[:120]


def localize_file(md_path, exports_dir, force=False):
    slug = slug_of(md_path)
    rel_dir = os.path.join("assets", slug)
    abs_dir = os.path.join(exports_dir, rel_dir)
    text = open(md_path, encoding="utf-8").read()

    # 收集外链
    urls = []
    for m in MD_IMG.finditer(text):
        urls.append(m.group(2).strip())
    for m in HTML_IMG.finditer(text):
        urls.append(m.group(1).strip())
    # 去重保序
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)

    if not uniq:
        return {"file": md_path, "images": 0, "downloaded": 0, "failed": 0, "note": "no external images"}

    os.makedirs(abs_dir, exist_ok=True)
    # 映射：url -> 本地相对路径（相对于 md 文件所在目录）
    counter = 0
    url_map = {}
    downloaded = 0
    failed = 0
    for u in uniq:
        ext = ext_from_url(u) or ".img"
        counter += 1
        local_name = "%02d%s" % (counter, ext) if ext != ".img" else "%02d.img" % counter
        # 若 URL 末尾有可读文件名且不太长，优先用原名
        base = os.path.basename(urllib.parse.urlparse(u).path)
        if base and len(base) <= 80 and "." in base:
            local_name = base
        local_abs = os.path.join(abs_dir, local_name)
        ok, info = download(u, local_abs)
        if ok:
            downloaded += 1
            rel = rel_dir + "/" + local_name
            url_map[u] = rel
        else:
            failed += 1
            print("  ⚠️ 下载失败 [%s]: %s" % (u, info))

    # 改写引用（仅改写外链）
    def repl_md(m):
        alt, url = m.group(1), m.group(2).strip()
        if url in url_map:
            return "![%s](%s)" % (alt, url_map[url])
        return m.group(0)

    def repl_html(m):
        tag = m.group(0)
        url = m.group(1).strip()
        if url in url_map:
            return tag.replace(url, url_map[url])
        return tag

    new_text = MD_IMG.sub(repl_md, text)
    new_text = HTML_IMG.sub(repl_html, new_text)

    if new_text != text:
        open(md_path, "w", encoding="utf-8").write(new_text)
        changed = True
    else:
        changed = False

    return {
        "file": md_path,
        "images": len(uniq),
        "downloaded": downloaded,
        "failed": failed,
        "rewritten": changed,
    }


def main():
    args = sys.argv[1:]
    root = None
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--root":
            root = args[i + 1]
            i += 2
        elif args[i] == "--force":
            force = True
            i += 1
        else:
            i += 1
    root = find_root(root)
    exports_dir = os.path.join(root, "wechat_exports")
    if not os.path.isdir(exports_dir):
        print("NO_EXPORTS_DIR: %s" % exports_dir)
        sys.exit(0)

    md_files = sorted(
        f for f in os.listdir(exports_dir)
        if f.lower().endswith(".md") and f.lower() != "readme.md"
    )
    if not md_files:
        print("NO_ARTICLES")
        sys.exit(0)

    print("WECHAT_EXPORTS_ROOT: %s" % exports_dir)
    print("FOUND_ARTICLES: %d" % len(md_files))
    total_dl = 0
    total_fail = 0
    for f in md_files:
        p = os.path.join(exports_dir, f)
        r = localize_file(p, exports_dir, force=force)
        if r.get("images"):
            print("  - %s | 外链图 %d, 下载 %d, 失败 %d, 改写=%s" % (
                f, r["images"], r["downloaded"], r["failed"], r.get("rewritten")))
            total_dl += r["downloaded"]
            total_fail += r["failed"]
        else:
            print("  - %s | 无外链图" % f)

    print("SUMMARY: 下载 %d 张, 失败 %d 张" % (total_dl, total_fail))
    sys.exit(0)


if __name__ == "__main__":
    main()
