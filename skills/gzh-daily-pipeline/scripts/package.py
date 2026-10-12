#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 gzh-daily-pipeline 打包成自包含的分发包。

背景：日常开发采用「扁平」结构——调度器与环节技能同级放在 skills/ 下，
每个环节技能既能被流水线调用，也能独立触发。但这样单独把调度器复制出去会断链
（../topic-collector 指向的目标不在包里）。本脚本解决分发问题：

  源结构（开发用）               产物结构（分发用）
  skills/                        dist/gzh-daily-pipeline/
    gzh-daily-pipeline/            SKILL.md（引用已改写）
      SKILL.md  ── ../topic-collector  skills/
    topic-collector/                 topic-collector/
    topic-generator/                 topic-generator/
    ...                              ...

做的事：
  1. 复制包体（SKILL.md / README / scripts / assets）
  2. 复制项目根 config/（platforms.json 与 pipeline.env.example；**pipeline.env 含密钥会被排除**）
  3. 把依赖技能复制进包内 skills/
  4. 把 SKILL.md 里的 ../<dep>/ 改写为 ./skills/<dep>/
  5. 可选：按目标安装位改写写死的绝对路径（config/ 指向包内，不走项目根兜底）
  6. 校验产物内引用可达、config 随包，并列出仍需人工处理的绝对路径

安全：绝不复制含密钥的文件（`.env`、`config/pipeline.env`），只复制 `config/pipeline.env.example`。
      validate 会再次扫描产物，发现密钥文件即告警。

用法：
  python3 scripts/package.py
  python3 scripts/package.py --out /tmp/dist
  python3 scripts/package.py --install-root ~/.workbuddy/skills
  python3 scripts/package.py --with-illustrations
"""

import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.dirname(HERE)                       # skills/gzh-daily-pipeline
SKILLS_DIR = os.path.dirname(PKG_DIR)                 # skills/
PROJECT_ROOT = os.path.dirname(SKILLS_DIR)            # 项目根

PKG_NAME = os.path.basename(PKG_DIR)

# 必需依赖：缺失即报错退出
DEPS = ["topic-collector", "topic-generator", "topic-reviewer",
        "gzh-write-enhanced", "公众号文章转多平台"]
# 可选依赖：缺失只告警
OPTIONAL_DEPS = ["ian-xiaohei-illustrations"]

# 复制时排除（密钥文件永不复制：.env / config/pipeline.env 都含 Token / API Key，
# 其 .bak 等备份变体同样含密钥，必须一并排除；但 .example 占位文件是安全的，需保留）
EXCLUDE = shutil.ignore_patterns(".env", "pipeline.env", "*.bak*", "__pycache__", ".DS_Store",
                                 "*.pyc", ".git", "dist", "wechat_exports")

# 内容目录：SKILL.md 里 `../assets/` 这类引用指向的是文章/配图产物目录，
# 不是依赖技能。它们本来就在包外（配图是内容产物，不该随技能包分发），
# 属于预期行为，不能当成「依赖没被打包」来告警。
CONTENT_DIRS = {"assets", "articles", "topics", "wechat_exports"}

# 源文件中写死的绝对路径前缀（本机专用，分发前需改写）
ABS_PREFIXES = [PROJECT_ROOT]


def log(msg=""):
    print(msg)


def warn(msg):
    print("WARN  %s" % msg, file=sys.stderr)


def copy_tree(src, dst, label):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=EXCLUDE)
    n = sum(len(f) for _, _, f in os.walk(dst))
    log("  复制 %-28s %2d 个文件" % (label, n))


def rewrite_refs(text, deps):
    """把 ../<dep>/ 改写为 ./skills/<dep>/。"""
    for d in deps:
        text = text.replace("../%s/" % d, "./skills/%s/" % d)
    return text


def rewrite_abs(text, install_root, work_dir=""):
    """按锚点精确改写写死的绝对路径。

    不能用「项目根 -> 安装根」的粗暴前缀替换：那会把
    <根>/articles 变成 <安装根>/articles、<根>/skills/gzh-daily-pipeline
    变成 <安装根>/skills/gzh-daily-pipeline，两个都是错的。
    必须逐个锚点映射，且长锚点优先。
    """
    target = os.path.expanduser(install_root.rstrip("/"))
    pairs = [(os.path.join(PROJECT_ROOT, "skills", PKG_NAME),
              os.path.join(target, PKG_NAME))]
    if work_dir:
        pairs.append((os.path.join(PROJECT_ROOT, "articles"),
                      os.path.expanduser(work_dir.rstrip("/"))))
    # 共享配置随包分发到 <安装根>/<包名>/config/，所以不能走下面的项目根兜底
    pairs.append((os.path.join(PROJECT_ROOT, "config"),
                  os.path.join(target, PKG_NAME, "config")))
    pairs.append((PROJECT_ROOT, target))          # 兜底：其余项目根路径
    for src, dst in pairs:
        text = text.replace(src, dst)
    return text


def find_abs_paths(text):
    """找出仍指向本机的绝对路径，供人工确认。"""
    hits = set()
    for p in ABS_PREFIXES:
        for m in re.finditer(re.escape(p) + r"[^\s`\)\"';,]*", text):
            hits.add(m.group(0))
    return sorted(hits)


def validate(dist_pkg, deps):
    """校验产物内的相对引用是否可达，返回 (ok, 待处理绝对路径)。"""
    skill_md = os.path.join(dist_pkg, "SKILL.md")
    text = open(skill_md, encoding="utf-8").read()
    ok = True

    # 0. 共享配置是否随包（平台开关的唯一数据源）
    cfg_json = os.path.join(dist_pkg, "config", "platforms.json")
    if os.path.exists(cfg_json):
        log("  共享配置: config/platforms.json 已随包")
    else:
        warn("缺少 config/platforms.json —— 平台开关唯一数据源未随包分发，S5/S6 将读不到 enabled")
        ok = False

    # 0b. 安全红线：密钥文件（含备份变体）是否被误打包
    def _looks_secret(name):
        if name == ".env" or name == "pipeline.env":
            return True
        if name.endswith(".bak") or ".bak" in name:
            return True
        # pipeline.env.* 变体（如 .bak-20261012）含密钥；.example 是占位，安全
        if name.startswith("pipeline.env.") and name != "pipeline.env.example":
            return True
        return False

    leaked = []
    for dirpath, _, files in os.walk(dist_pkg):
        for name in files:
            if _looks_secret(name):
                leaked.append(os.path.relpath(os.path.join(dirpath, name), dist_pkg))
    if leaked:
        warn("密钥文件被打包进产物，立即删除: %s" % ", ".join(leaked))
        ok = False
    else:
        log("  安全检查: 未发现密钥文件（pipeline.env / .env 及其 .bak 备份变体）")

    # 1. 相对引用可达性（跳过文档里的占位符写法，如 ./skills/<skill>/）
    refs = set(re.findall(r"`(\./[^`]+)`", text))
    refs = {r for r in refs if "<" not in r}
    for r in sorted(refs):
        p = os.path.normpath(os.path.join(dist_pkg, r))
        if not os.path.exists(p):
            warn("引用不可达: %s" % r)
            ok = False
    if refs:
        log("  引用校验: %d 条相对引用，%s" % (len(refs), "全部可达" if ok else "存在不可达"))

    # 2. 是否残留 ../ 依赖引用（说明有依赖没被打包）
    #    排除占位符写法，以及内容目录（../assets/ 指向配图产物，不随技能包分发，属预期）
    left = sorted(set(re.findall(r"\.\./([A-Za-z0-9_\u4e00-\u9fff-]+)/", text)))
    left = [x for x in left if x != "<skill>" and x not in CONTENT_DIRS]
    if left:
        warn("产物仍残留外部依赖引用: %s" % ", ".join(left))
        ok = False

    # 3. 依赖技能自身是否引用了包外兄弟（会断链）
    for d in deps:
        dep_md = os.path.join(dist_pkg, "skills", d, "SKILL.md")
        if not os.path.exists(dep_md):
            continue
        dt = open(dep_md, encoding="utf-8").read()
        out = sorted(set(re.findall(r"\.\./([A-Za-z0-9_\u4e00-\u9fff-]+)/", dt)))
        if out:
            warn("%s 引用包外: %s（需一并打包或手工调整）" % (d, ", ".join(out)))

    return ok, find_abs_paths(text)


def main():
    ap = argparse.ArgumentParser(description="打包 gzh-daily-pipeline 为自包含分发包")
    ap.add_argument("--out", default=os.path.join(PROJECT_ROOT, "dist"),
                    help="输出根目录，默认 <项目根>/dist")
    ap.add_argument("--install-root", default="",
                    help="目标安装位，用于改写写死的技能包绝对路径，如 ~/.workbuddy/skills")
    ap.add_argument("--work-dir", default="",
                    help="目标机器上的产物目录，用于改写 WORK_DIR，如 ~/my-gzh-articles")
    ap.add_argument("--with-illustrations", action="store_true",
                    help="一并打包可选的配图技能 ian-xiaohei-illustrations")
    args = ap.parse_args()

    # 依赖预检
    missing = [d for d in DEPS if not os.path.isdir(os.path.join(SKILLS_DIR, d))]
    if missing:
        print("ERROR 缺少必需依赖: %s" % ", ".join(missing), file=sys.stderr)
        print("       期望位置: %s/<skill>/" % SKILLS_DIR, file=sys.stderr)
        return 2

    deps = list(DEPS)
    if args.with_illustrations:
        for d in OPTIONAL_DEPS:
            if os.path.isdir(os.path.join(SKILLS_DIR, d)):
                deps.append(d)
            else:
                warn("可选依赖未安装，跳过: %s" % d)

    out_root = os.path.abspath(os.path.expanduser(args.out))
    dist_pkg = os.path.join(out_root, PKG_NAME)

    log("打包 gzh-daily-pipeline")
    log("  源    : %s" % PKG_DIR)
    log("  产物  : %s" % dist_pkg)
    log()

    # 1. 复制包体
    if os.path.exists(dist_pkg):
        shutil.rmtree(dist_pkg)
    os.makedirs(out_root, exist_ok=True)
    copy_tree(PKG_DIR, dist_pkg, "包体（scripts/assets/README）")

    # 1b. 复制共享配置（平台开关的唯一数据源，必须随包，否则 S5/S6 读不到 enabled）
    cfg_src = os.path.join(PROJECT_ROOT, "config")
    if os.path.isdir(cfg_src):
        copy_tree(cfg_src, os.path.join(dist_pkg, "config"), "共享配置 config/")
    else:
        warn("未找到 %s，打包后 config/platforms.json 缺失，平台开关将失效" % cfg_src)

    bundled = set()
    for d in deps:
        src = os.path.join(SKILLS_DIR, d)
        copy_tree(src, os.path.join(dist_pkg, "skills", d), "依赖 %s" % d)
        bundled.add(d)

    # 2. 改写引用
    skill_md = os.path.join(dist_pkg, "SKILL.md")
    text = open(skill_md, encoding="utf-8").read()
    before = text
    text = rewrite_refs(text, deps)
    if args.install_root:
        text = rewrite_abs(text, args.install_root, args.work_dir)
        log("  改写路径: 技能包 -> %s%s"
            % (os.path.join(args.install_root, PKG_NAME),
               "，产物目录 -> %s" % args.work_dir if args.work_dir else "（WORK_DIR 未改）"))
    if text != before:
        open(skill_md, "w", encoding="utf-8").write(text)
        log("  改写引用: ../<dep>/ -> ./skills/<dep>/%s"
            % ("，绝对路径 -> %s" % args.install_root if args.install_root else ""))

    # 3. 复制人设文件（唯一副本在写作技能 resources 下，不存在则不附带）
    #    历史原因：曾另有项目根 author_voice.md 作兜底。该份已于 2026-10-11 删除并归档
    #    （内容被下面这份完整覆盖），人设改为单点定义，不再保留第二份来源。
    voice = os.path.join(SKILLS_DIR, "gzh-write-enhanced", "resources", "author_voice.md")
    if os.path.exists(voice):
        shutil.copy2(voice, os.path.join(dist_pkg, "author_voice.md"))
        log("  附带人设: author_voice.md（取自 gzh-write-enhanced/resources）")
    else:
        log("  未附带人设: gzh-write-enhanced/resources/author_voice.md 不存在")
        log("  分发到其他机器后需在目标机器补配该文件，否则写作环节回退到第三方人设")

    # 4. 校验
    log()
    ok, abs_paths = validate(dist_pkg, deps)

    if abs_paths and not args.install_root:
        log()
        log("  注意：产物内仍有以下本机绝对路径，安装到别的机器需手工替换")
        log("      （或用 --install-root <目标目录> 让脚本自动改写）")
        for p in abs_paths[:6]:
            log("      %s" % p)

    log()
    total = sum(len(f) for _, _, f in os.walk(dist_pkg))
    log("完成：%s（%d 个文件，依赖 %d 个）" % (dist_pkg, total, len(deps)))
    if not ok:
        warn("存在告警，请检查上面的 WARN 后再分发")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
