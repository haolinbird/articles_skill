#!/usr/bin/env python3
"""topic-collector 抓取脚本：从海外与国内源采集 AI 编程相关热点。

只用标准库，无需安装依赖。输出 JSON 到 stdout，便于上层整理成 Markdown。

用法：
    python3 fetch_sources.py                        # 默认：昨天 00:00:00 至今
    python3 fetch_sources.py --since 2026-10-04     # 指定起始日 00:00:00 至今
    python3 fetch_sources.py --hours 24             # 退化为滑动窗口（调试用）
    python3 fetch_sources.py --out /tmp/x.json      # 同时写入文件
    python3 fetch_sources.py --raw                  # 输出未过滤的全量条目

时间窗口口径（重要）：
    默认按自然日切分，而不是"最近 N 小时"。任意时刻运行，起点都固定在昨天 00:00:00
    （UTC+8），终点为当前时刻。这样同一天内多次运行的结果只会增加、不会因窗口滑动
    而丢失条目；跨天运行则自动滚动到新的起点。
"""

import argparse
import datetime
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

CST = datetime.timezone(datetime.timedelta(hours=8))
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"}

# 强信号：命中任一即视为 AI 编程相关
CORE_KW = ["claude", "cursor", "copilot", "codex", "coding", "vibe", "agent",
           "llm", "智能体", "编程", "大模型", "人工智能", "harness"]

# 弱信号：单独命中不足以判定，需至少命中两个
WEAK_KW = ["code", "ai", "gpt", "gemini", "developer", "programming", "software",
           "代码", "通义", "文心", "glm", "deepseek", "kimi", "sdk", "editor"]

BIZ_KW = ["落地", "企业", "团队", "研发效能", "提效", "降本", "生产环境", "内部",
          "中台", "规范", "实践", "转型", "规模化", "试点", "工程", "交付",
          "效率", "架构", "治理", "质量", "review", "重构", "效能", "harness", "loop"]

# 与公众号「AI编程应用实战」定位不符：底层模型研发、纯学术、融资
EXCLUDE_KW = ["training", "fine-tun", "pretrain", "benchmark accuracy",
              "transformer architecture", "raises", "funding round", "ipo",
              "chip", "gpu cluster", "推理引擎", "模型训练", "预训练"]

FEEDS_CN = [
    ("掘金", "https://juejin.cn/rss", "中"),
    ("InfoQ中国", "https://www.infoq.cn/feed", "中"),
    ("开源中国", "https://www.oschina.net/news/rss", "中"),
    ("美团技术", "https://tech.meituan.com/feed/", "中"),
]

HN_QUERIES = ["Claude", "Cursor", "Copilot", "Codex", "AI coding",
              "coding agent", "vibe coding", "LLM", "developer"]

GH_REPOS = ["anthropics/claude-code", "openai/codex"]
PH_FEED = "https://www.producthunt.com/feed"
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


def http_get(url, timeout=25, retries=2):
    """带重试的 GET。失败只告警不抛出，由调用方决定降级。

    重试是必要的：GitHub releases.atom 等源偶发超时或 502，单源失败会让该源
    静默返回 0 条——不报错、只是数据消失，比崩溃更难发现。
    """
    last = ""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = str(e)[:90]
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    print("WARN %s -> %s" % (url, last), file=sys.stderr)
    return None


def parse_time(s):
    if not s:
        return None
    s = s.strip()
    for f in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
              "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"]:
        try:
            d = datetime.datetime.strptime(s, f)
            return d if d.tzinfo else d.replace(tzinfo=CST)
        except ValueError:
            pass
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_feed(raw):
    """同时兼容 RSS(item) 与 Atom(entry)。返回 [(title, link, pub, desc)]。"""
    try:
        text = raw.decode("utf-8", "ignore")
    except UnicodeDecodeError:
        text = raw.decode("gbk", "ignore")
    text = re.sub(r"^\s+", "", text)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        print("WARN feed parse: %s" % str(e)[:80], file=sys.stderr)
        return []
    out = []
    for it in root.iter("item"):
        out.append((it.findtext("title") or "", it.findtext("link") or "",
                    it.findtext("pubDate") or "", it.findtext("description") or ""))
    for e in root.findall("a:entry", ATOM_NS):
        link = ""
        for l in e.findall("a:link", ATOM_NS):
            if l.get("rel") in (None, "alternate"):
                link = l.get("href", "")
                break
        pub = (e.findtext("a:published", "", ATOM_NS)
               or e.findtext("a:updated", "", ATOM_NS) or "")
        out.append((e.findtext("a:title", "", ATOM_NS) or "", link, pub,
                    e.findtext("a:content", "", ATOM_NS)
                    or e.findtext("a:summary", "", ATOM_NS) or ""))
    return out


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def keywords_of(text):
    low = text.lower()
    core = [k for k in CORE_KW if k in low]
    weak = [k for k in WEAK_KW if k in low]
    return {
        "ai": core + weak,
        "core": core,
        "weak": weak,
        "biz": [k for k in BIZ_KW if k in low],
        "relevant": bool(core) or len(weak) >= 2,
        "excluded": [k for k in EXCLUDE_KW if k in low],
    }


def collect_hn(ts_from):
    seen, out = set(), []
    for q in HN_QUERIES:
        url = ("https://hn.algolia.com/api/v1/search_by_date?query="
               + urllib.parse.quote(q)
               + "&tags=story&numericFilters=created_at_i%3E" + str(ts_from)
               + "&hitsPerPage=100")
        raw = http_get(url)
        if not raw:
            continue
        try:
            hits = json.loads(raw.decode("utf-8", "ignore")).get("hits", [])
        except ValueError:
            continue
        for h in hits:
            oid = h.get("objectID")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            out.append({
                "source": "hackernews", "source_label": "Hacker News",
                "title": h.get("title") or "",
                "url": h.get("url") or "",
                "discussion_url": "https://news.ycombinator.com/item?id=%s" % oid,
                "published_at": datetime.datetime.fromtimestamp(
                    h.get("created_at_i", 0), CST).strftime("%Y-%m-%d %H:%M"),
                "heat": {"points": h.get("points"), "comments": h.get("num_comments")},
                "summary": "", "lang": "英",
            })
    return out


def collect_github_api(repo, ts_from_dt):
    """GitHub Releases 的备用路径。

    releases.atom 会间歇性 502 或隧道失败（实测返回 000），此时该源会静默归零。
    API 路径更稳，代价是未认证限额 60 次/小时——每天跑几次足够。
    """
    raw = http_get("https://api.github.com/repos/%s/releases?per_page=20" % repo)
    if not raw:
        return []
    try:
        rels = json.loads(raw.decode("utf-8", "ignore"))
    except ValueError:
        return []
    if not isinstance(rels, list):
        return []
    out = []
    for r in rels:
        d = parse_time(r.get("published_at") or r.get("created_at") or "")
        if not d or d < ts_from_dt:
            continue
        out.append({
            "source": "github_releases",
            "source_label": "GitHub Releases (%s)" % repo,
            "title": "%s %s" % (repo.split("/")[-1],
                                r.get("tag_name") or r.get("name") or ""),
            "url": r.get("html_url") or "", "discussion_url": "",
            "published_at": d.astimezone(CST).strftime("%Y-%m-%d %H:%M"),
            "heat": None, "summary": strip_html(r.get("body") or "")[:200],
            "lang": "英",
        })
    return out


def collect_github(ts_from_dt):
    out = []
    for repo in GH_REPOS:
        raw = http_get("https://github.com/%s/releases.atom" % repo, retries=1)
        if raw is None:
            # atom 不可达 → 回退 API，避免该源静默归零
            print("INFO %s atom 不可用，回退 GitHub API" % repo, file=sys.stderr)
            out.extend(collect_github_api(repo, ts_from_dt))
            continue
        for t, link, pub, desc in parse_feed(raw):
            d = parse_time(pub)
            if not d or d < ts_from_dt:
                continue
            out.append({
                "source": "github_releases", "source_label": "GitHub Releases (%s)" % repo,
                "title": "%s %s" % (repo.split("/")[-1], t),
                "url": link, "discussion_url": "",
                "published_at": d.astimezone(CST).strftime("%Y-%m-%d %H:%M"),
                "heat": None, "summary": strip_html(desc)[:200], "lang": "英",
            })
    return out


def collect_ph(ts_from_dt):
    raw = http_get(PH_FEED)
    if not raw:
        return []
    out = []
    for t, link, pub, desc in parse_feed(raw):
        d = parse_time(pub)
        if not d or d < ts_from_dt:
            continue
        out.append({
            "source": "producthunt", "source_label": "Product Hunt",
            "title": t, "url": link, "discussion_url": "",
            "published_at": d.astimezone(CST).strftime("%Y-%m-%d %H:%M"),
            "heat": None, "summary": strip_html(desc)[:200], "lang": "英",
        })
    return out


def collect_cn(ts_from_dt):
    out = []
    for label, url, lang in FEEDS_CN:
        raw = http_get(url)
        if not raw:
            continue
        for t, link, pub, desc in parse_feed(raw):
            d = parse_time(pub)
            if not d or d < ts_from_dt:
                continue
            out.append({
                "source": label, "source_label": label,
                "title": t.strip(), "url": link.strip(), "discussion_url": "",
                "published_at": d.astimezone(CST).strftime("%Y-%m-%d %H:%M"),
                "heat": None, "summary": strip_html(desc)[:250], "lang": lang,
            })
    return out


def resolve_window(since, hours):
    """计算采集窗口。默认按自然日：昨天 00:00:00 至今。

    返回 (start_dt, now_dt, mode_label)。hour 与 since 互斥，由 argparse 保证。
    """
    now = datetime.datetime.now(CST)
    if hours is not None:
        # 调试用：退化为"最近 N 小时"滑动窗口
        return now - datetime.timedelta(hours=hours), now, "rolling_%dh" % hours
    if since:
        try:
            day = datetime.datetime.strptime(since, "%Y-%m-%d").date()
        except ValueError:
            raise SystemExit("--since 格式应为 YYYY-MM-DD，实际得到：%s" % since)
    else:
        day = now.date() - datetime.timedelta(days=1)
    start = datetime.datetime.combine(day, datetime.time(0, 0, 0), tzinfo=CST)
    return start, now, "day_start"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--since", default="",
                   help="起始日期 YYYY-MM-DD，取其 00:00:00 作为窗口起点")
    g.add_argument("--hours", type=int, default=None,
                   help="退化为「最近 N 小时」滑动窗口，仅调试用")
    ap.add_argument("--out", default="")
    ap.add_argument("--raw", action="store_true", help="输出未过滤的全量条目")
    args = ap.parse_args()

    now = datetime.datetime.now(CST)
    ts_from_dt, now, window_mode = resolve_window(args.since, args.hours)
    ts_from = int(ts_from_dt.timestamp())
    if ts_from_dt > now:
        raise SystemExit("窗口起点晚于当前时刻，请检查 --since")

    items = (collect_hn(ts_from) + collect_github(ts_from_dt)
             + collect_ph(ts_from_dt) + collect_cn(ts_from_dt))

    for it in items:
        blob = "%s %s" % (it["title"], it["summary"])
        it["keywords"] = keywords_of(blob)
        it["has_url"] = bool(it["url"] or it["discussion_url"])

    if not args.raw:
        items = [i for i in items
                 if i["keywords"]["relevant"] and not i["keywords"]["excluded"]]

    items.sort(key=lambda x: x["published_at"], reverse=True)

    by_source = {}
    for it in items:
        by_source[it["source"]] = by_source.get(it["source"], 0) + 1

    result = {
        "window": {"from": ts_from_dt.strftime("%Y-%m-%d %H:%M:%S"),
                   "to": now.strftime("%Y-%m-%d %H:%M:%S"),
                   "mode": window_mode,
                   "span_hours": round((now - ts_from_dt).total_seconds() / 3600, 2)},
        "total": len(items),
        "by_source": by_source,
        "items": items,
    }

    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("written: %s" % args.out, file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
