#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
产物保留策略：清理过期的流水线产物（articles / assets / topics）。

为什么需要：这三个目录只增不减。articles 每天多 5–12 个 md，assets 每天一个目录（含原图），
跑几个月就会堆到几百 MB 且难以翻找。

安全设计（默认不删任何东西）：
  - 不带 --apply → **只打印清单**（dry-run），不动文件
  - --apply      → 移动到 `.archive/cleanup-<今天>/`（可找回）
  - --delete     → 真删除（必须显式加，且与 --apply 同时给才生效）

日期识别（认不出就跳过，绝不误伤）：
  articles/YYYYMMDD/          取目录名（8 位）
  assets/YYYYMMDD-<主题>/      取目录名前 8 位
  topics/YYYY-MM-DD.md         取文件名前 10 位

用法：
  python3 cleanup_products.py                      # 预览（默认 30 天）
  python3 cleanup_products.py --days 7             # 预览 7 天前
  python3 cleanup_products.py --apply              # 归档到 .archive/cleanup-<日期>/
  python3 cleanup_products.py --apply --delete     # 真删除

退出码：0 正常；1 参数错误
"""

import argparse
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# 产物根目录（scripts/ → skills/gzh-daily-pipeline/ → skills/ → 项目根）
ROOT = Path(__file__).resolve().parents[3]

TARGETS = ("articles", "assets", "topics")
PATTERNS = [
    (r"^(\d{8})$", "%Y%m%d"),          # articles/20261013/ (目录)
    (r"^(\d{8})-", "%Y%m%d"),          # assets/20261012-xxx/
    (r"^(\d{4}-\d{2}-\d{2})\.md$", "%Y-%m-%d"),  # topics/2026-10-12.md
]


def parse_date(name: str):
    for pat, fmt in PATTERNS:
        m = re.match(pat, name)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt).date()
            except ValueError:
                return None
    return None


def scan(days: int):
    """返回 (过期条目, 无法识别条目)"""
    cutoff = date.today() - timedelta(days=days)
    expired, unknown = [], []
    for d in TARGETS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in sorted(base.iterdir()):
            dt = parse_date(p.name)
            if dt is None:
                unknown.append(p)
            elif dt < cutoff:
                expired.append((p, dt))
    return expired, unknown


def size_of(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size


def human(n: int) -> str:
    return f"{n/1024:.0f} KB" if n < 1024 * 1024 else f"{n/1024/1024:.1f} MB"


def main():
    ap = argparse.ArgumentParser(description="清理过期流水线产物（默认 dry-run）")
    ap.add_argument("--days", type=int, default=30, help="保留最近 N 天，默认 30")
    ap.add_argument("--apply", action="store_true", help="实际执行（否则只预览）")
    ap.add_argument("--delete", action="store_true", help="真删除而非归档（需与 --apply 同用）")
    args = ap.parse_args()

    if args.delete and not args.apply:
        print("❌ --delete 必须与 --apply 同时使用（防止误删）")
        return 1

    expired, unknown = scan(args.days)
    total = sum(size_of(p) for p, _ in expired)

    mode = "删除" if (args.apply and args.delete) else ("归档" if args.apply else "预览")
    print(f"模式: {mode}｜保留最近 {args.days} 天｜截止 {date.today() - timedelta(days=args.days)}")
    print(f"项目根: {ROOT}\n")

    if not expired:
        print("✅ 没有过期产物，无需清理")
    else:
        print(f"过期产物 {len(expired)} 项，共 {human(total)}：")
        for p, dt in expired:
            print(f"  [{dt}] {p.relative_to(ROOT)}  ({human(size_of(p))})")

    if unknown:
        print(f"\n⚠️ 日期无法识别、已跳过（{len(unknown)} 项，不会动它们）：")
        for p in unknown[:10]:
            print(f"  {p.relative_to(ROOT)}")

    if not args.apply or not expired:
        print("\n（这是预览，未改动任何文件。加 --apply 归档，或 --apply --delete 真删除）")
        return 0

    if args.delete:
        for p, _ in expired:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        print(f"\n✅ 已删除 {len(expired)} 项")
    else:
        dest_root = ROOT / ".archive" / f"cleanup-{date.today():%Y%m%d}"
        dest_root.mkdir(parents=True, exist_ok=True)
        for p, _ in expired:
            dest = dest_root / p.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dest))
        print(f"\n✅ 已归档 {len(expired)} 项 → {dest_root.relative_to(ROOT)}/")
        print("   （确认不再需要后可手动删掉该目录）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
