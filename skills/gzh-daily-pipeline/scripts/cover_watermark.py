#!/usr/bin/env python3
"""
cover_watermark.py — 遮盖智谱 CogView 系列图片右下角的「AI生成」水印。

背景：智谱水印为服务端强制，API 参数（watermark_enabled / watermark）均无法关闭。
处理方式：在右下角水印区域绘制白色矩形遮盖。配合 prompt 末尾加
「画面右下角保持纯白空白，不要画任何东西」可避免切断画面线条。

开关：读 GZH_COVER_WATERMARK（config/pipeline.env），true 才执行，否则原样退出（exit 0）。
用法：python3 cover_watermark.py <图片1> [图片2 ...]（原地覆盖保存）
依赖：Pillow（PIL）。需要能 import PIL 的解释器执行。
退出码：0 成功或跳过；1 无图片参数；2 缺 Pillow；3 开关未开启；
        4 某图片处理失败（其余图片仍会处理完）。
"""
import os
import sys

# 水印遮盖区域（相对比例，1024x1024 实测 [845,945]-[1024,1024] 有效；
# 按比例适配其他分辨率）。x0, y0, x1, y1
COVER_BOX_RATIO = (0.825, 0.923, 1.0, 1.0)
ENV_KEY = "GZH_COVER_WATERMARK"


def find_project_root():
    """向上查找含 config/pipeline.env 的目录（与 load_config.cjs 同规则）。"""
    env_rel = os.path.join("config", "pipeline.env")
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.exists(os.path.join(d, env_rel)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return None


def switch_enabled():
    """读 GZH_COVER_WATERMARK：进程环境变量 > config/pipeline.env。未配置视为 false。"""
    source = "环境变量"
    v = os.environ.get(ENV_KEY)
    if v is None:
        source = "config/pipeline.env"
        root = find_project_root()
        if root:
            env_file = os.path.join(root, "config", "pipeline.env")
            try:
                with open(env_file, encoding="utf-8") as f:
                    for line in f:
                        m = line.split("=", 1)
                        if len(m) == 2 and m[0].strip() == ENV_KEY:
                            v = m[1].strip()
                            break
            except OSError:
                source = "（配置文件读取失败）"
    if v is None:
        source = "（未配置）"
    return str(v).strip().lower() in ("true", "1", "yes", "on"), source


def cover(path):
    from PIL import Image, ImageDraw

    im = Image.open(path)
    has_alpha = im.mode in ("RGBA", "LA")
    if has_alpha:
        im = im.convert("RGBA")
        overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
    else:
        im = im.convert("RGB")
        d = ImageDraw.Draw(im)

    w, h = im.size
    x0, y0, x1, y1 = COVER_BOX_RATIO
    box = [round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)]
    if has_alpha:
        d.rectangle(box, fill=(255, 255, 255, 255))
        im = Image.alpha_composite(im, overlay).convert("RGB")
    else:
        d.rectangle(box, fill=(255, 255, 255))

    save_kwargs = {"quality": 92} if path.lower().endswith((".jpg", ".jpeg")) else {}
    im.save(path, **save_kwargs)
    print(f"OK   已遮盖水印 {path} box={box}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "-h" in sys.argv or "--help" in sys.argv or not args:
        print(__doc__)
        return 0 if ("-h" in sys.argv or "--help" in sys.argv) else 1

    enabled, source = switch_enabled()
    if not enabled:
        print(f"跳过：{ENV_KEY}=false（来源：{source}），图片保持原样。")
        return 0  # 跳过不是失败，返回 0 保证 && 命令链不断

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("错误：缺 Pillow。请用带 Pillow 的解释器执行，"
              "或先安装：pip install pillow")
        return 2

    failed = 0
    for p in args:
        if not os.path.exists(p):
            print(f"FAIL 文件不存在: {p}")
            failed += 1
            continue
        try:
            cover(p)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {p}: {e}")
            failed += 1
    return 4 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
