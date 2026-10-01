# -*- coding: utf-8 -*-
r"""配置持久化：%APPDATA%\CountdownDesktop\config.json

倒计时类型（exam_type）：
  gaokao  → DEFAULT_URL（高考倒计时，原默认）
  zhongkao → JUNIOR_URL（中考倒计时）
  custom  → 壁纸/屏保各自使用保存的自定义地址（留空则回退高考默认）
"""
import json
import os

DEFAULT_URL = "https://zztool.free.nf/countdown"        # 高考倒计时（原默认链接）
JUNIOR_URL = "https://zztool.free.nf/countdown-junior"  # 中考倒计时
EXAM_TYPES = ("gaokao", "zhongkao", "custom")
EXAM_URLS = {"gaokao": DEFAULT_URL, "zhongkao": JUNIOR_URL}
EXAM_LABELS = {"gaokao": "高考倒计时", "zhongkao": "中考倒计时", "custom": "自定义地址"}

# 图片/视频画幅模式：cover=铺满裁剪 | contain=完整显示留黑边 | fill=拉伸铺满
FIT_MODES = ("cover", "contain", "fill")
FIT_LABELS = {"cover": "铺满全屏（裁剪）", "contain": "保留原内容（黑边）", "fill": "铺满全屏（拉伸）"}

DEFAULTS = {
    "exam_type": "gaokao",
    "wallpaper": {
        "enabled": True,
        "url": DEFAULT_URL,
        "fit": "cover",   # 仅对图片/视频源生效
        "mute": True,     # 壁纸默认静音
    },
    "screensaver": {
        "enabled": True,
        "url": DEFAULT_URL,
        "timeout": 600,
        "fit": "cover",
        "mute": True,     # 屏保默认静音
    },
    "playback": {
        "video_loop": True,   # 视频循环播放
    },
    "auto_check_update": True,  # 启动时自动检查更新（仅查询提示）
    "run_at_startup": False,
}


def config_dir() -> str:
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                     "CountdownDesktop")
    os.makedirs(d, exist_ok=True)
    return d


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def default_url(exam_type: str = None) -> str:
    """倒计时预设地址：gaokao/zhongkao 返回对应预设，其余（custom/None）回退高考默认。"""
    return EXAM_URLS.get(exam_type, DEFAULT_URL)


def resolve_exam(cfg: dict) -> dict:
    """按 exam_type 把壁纸/屏保源解析为预设地址（custom 不做改动）。"""
    et = cfg.get("exam_type", "gaokao")
    if et in EXAM_URLS:
        cfg["wallpaper"]["url"] = EXAM_URLS[et]
        cfg["screensaver"]["url"] = EXAM_URLS[et]
    return cfg


def load() -> dict:
    """读取配置，缺省值补齐（深合并）。

    旧版（v3.1.2.0 及以前）配置没有 exam_type 字段：按存量 URL 推断一次，
    保证升级后行为与升级前完全一致——壁纸/屏保都是高考默认→gaokao，
    都是中考地址→zhongkao，其余（曾自定义过）→custom。
    """
    cfg = json.loads(json.dumps(DEFAULTS))
    data = None
    # 优先读主配置，损坏时尝试 .bak 备份
    for path in (config_path(), config_path() + ".bak"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            break
        except (OSError, ValueError):
            continue
    if data is None:
        return cfg
    for section, values in data.items():
        if isinstance(values, dict) and isinstance(cfg.get(section), dict):
            cfg[section].update(values)
        else:
            cfg[section] = values
    if "exam_type" not in data:
        wall, ss = cfg["wallpaper"]["url"], cfg["screensaver"]["url"]
        if wall == JUNIOR_URL and ss == JUNIOR_URL:
            cfg["exam_type"] = "zhongkao"
        elif wall == DEFAULT_URL and ss == DEFAULT_URL:
            cfg["exam_type"] = "gaokao"
        else:
            cfg["exam_type"] = "custom"
    return cfg


def save(cfg: dict) -> None:
    """原子写入：先写 .tmp，再 os.replace 覆盖主文件，同时保留 .bak 备份。"""
    main = config_path()
    tmp = main + ".tmp"
    bak = main + ".bak"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    # 旧主文件转备份（如果存在）
    try:
        if os.path.isfile(main):
            if os.path.isfile(bak):
                os.remove(bak)
            os.replace(main, bak)
    except OSError:
        pass
    os.replace(tmp, main)
