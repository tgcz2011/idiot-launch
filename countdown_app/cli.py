# -*- coding: utf-8 -*-
"""命令行参数：单次有效覆盖（不写入长期配置）。

用法示例（主程序 / 播放器均支持）：
  CountdownDesktop.exe --exam zhongkao
  CountdownDesktop.exe --exam custom --wallpaper-url https://example.com/a --screensaver-url https://example.com/b
  CountdownDesktop.exe --screensaver-timeout 300 --video-loop off

规则：
- 所有参数均为可选；未传的项沿用已保存配置。
- 覆盖只作用于本次运行的进程内存，退出后不写入 config.json；
  唯一例外：本次会话中用户手动打开设置并「保存」时，界面当前值会落盘（所见即所得）。
- 主进程会把解析出的参数透传给壁纸/屏保播放器子进程，保证二者使用同一覆盖配置；
  也可直接对播放器传参：run.py player wallpaper --exam zhongkao。
- 显式 --wallpaper-url/--screensaver-url 优先于 --exam 预设；
  只传地址不传 --exam 时，倒计时类型自动视为「自定义」。
- --exam gaokao/zhongkao 会自动启用壁纸与屏保（预设模式即用于显示倒计时，
  若此前用户关闭过壁纸，不自动启用会导致"选了中考却没壁纸"）。
"""
import argparse
import logging

log = logging.getLogger("cli")

USAGE = (
    "Countdown Desktop 命令行参数（全部单次有效，不写入长期设置）\n"
    "\n"
    "  --quit                             优雅退出正在运行的实例（不启动 GUI，供其他软件调用）\n"
    "  --exam gaokao|zhongkao|custom      倒计时类型：高考（默认）/ 中考 / 自定义\n"
    "  --wallpaper-url <URL>              壁纸源（网页地址或本地媒体文件路径）\n"
    "  --wallpaper-enabled on|off         是否启用动态壁纸\n"
    "  --wallpaper-fit cover|contain|fill 壁纸画幅（图片/视频源）\n"
    "  --wallpaper-mute on|off            壁纸静音\n"
    "  --screensaver-url <URL>            屏保源\n"
    "  --screensaver-enabled on|off       是否启用屏保\n"
    "  --screensaver-timeout <秒>         屏保空闲触发时长\n"
    "  --screensaver-fit cover|contain|fill 屏保画幅（图片/视频源）\n"
    "  --screensaver-mute on|off          屏保静音\n"
    "  --video-loop on|off                视频循环播放\n"
    "  --run-at-startup on|off            本次会话的开机自启显示状态（不写注册表）\n"
    "  --auto-check-update on|off         本次会话是否自动检查更新\n"
"  --settings                         启动后自动弹出设置窗口\n"
    "  --help / -h                        显示本帮助\n"
    "\n"
    "示例：\n"
    "  CountdownDesktop.exe --exam zhongkao\n"
    "  CountdownDesktop.exe --exam custom --wallpaper-url https://example.com\n"
    "  CountdownDesktop.exe --quit\n"
)


def _bool(v):
    """on/off/1/0/true/false/yes/no → bool，其余抛错。"""
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on", "y"):
        return True
    if s in ("0", "false", "no", "off", "n"):
        return False
    raise argparse.ArgumentTypeError("期望 on/off/true/false，收到 %r" % v)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="CountdownDesktop", add_help=True, allow_abbrev=False,
        description="单次有效参数覆盖（不写入长期设置）")
    p.add_argument("--exam", choices=("gaokao", "zhongkao", "custom"),
                   help="倒计时类型：gaokao（高考，默认）/ zhongkao（中考）/ custom（自定义地址）")
    p.add_argument("--wallpaper-url", metavar="URL", help="壁纸源地址")
    p.add_argument("--wallpaper-enabled", type=_bool, metavar="on|off")
    p.add_argument("--wallpaper-fit", choices=("cover", "contain", "fill"))
    p.add_argument("--wallpaper-mute", type=_bool, metavar="on|off")
    p.add_argument("--screensaver-url", metavar="URL", help="屏保源地址")
    p.add_argument("--screensaver-enabled", type=_bool, metavar="on|off")
    p.add_argument("--screensaver-timeout", type=int, metavar="秒")
    p.add_argument("--screensaver-fit", choices=("cover", "contain", "fill"))
    p.add_argument("--screensaver-mute", type=_bool, metavar="on|off")
    p.add_argument("--video-loop", type=_bool, metavar="on|off")
    p.add_argument("--run-at-startup", type=_bool, metavar="on|off")
    p.add_argument("--auto-check-update", type=_bool, metavar="on|off")
    p.add_argument("--settings", action="store_true", default=argparse.SUPPRESS,
                   help="启动后自动弹出设置窗口")
    return p


def parse_argv(argv) -> tuple:
    """解析命令行，返回 (overrides, problems)。

    - overrides：仅含用户显式传入的项（dict，键为 config 字段名）。
    - problems：无法识别的选项列表；解析整体失败时 problems 为含说明的列表。
    - argv 开头的非选项位置参数（player / wallpaper 等）会被跳过。
    """
    args = list(argv[1:])
    while args and not args[0].startswith("-"):
        args.pop(0)
    parser = build_parser()
    try:
        ns, unknown = parser.parse_known_args(args)
    except SystemExit as e:
        # --help 会打印用法并正常退出（code 0），此处仅吞掉，不报错
        if e.code in (0, None):
            return {}, []
        return {}, ["参数解析失败（%s）。可用 --help 查看全部参数。" % e.code]
    overrides = {}
    for key, val in vars(ns).items():
        if val is not None:
            overrides[key] = val
    problems = [a for a in unknown if a.startswith("-")]
    return overrides, problems


def serialize(overrides: dict) -> list:
    """把覆盖项序列化为 --key=value 形式，供播放器子进程复用。

    注意：--settings 是 store_true（不接受值），必须输出为 --settings 而非 --settings=true，
    否则 argparse 会报 "ignored explicit argument 'true'" 导致整个解析失败，
    连带着 --exam 等参数也被丢弃，子进程回退到读取本地配置。
    """
    out = []
    for key, val in overrides.items():
        if key == "settings":
            if val:
                out.append("--settings")
            continue
        if isinstance(val, bool):
            val = "true" if val else "false"
        out.append("--%s=%s" % (key.replace("_", "-"), val))
    return out


def apply(overrides: dict, cfg: dict) -> dict:
    """把 CLI 覆盖应用到配置（仅内存，不落盘）。

    顺序：exam 预设解析 → 显式 URL 覆盖（优先）。未传 --exam 但有显式
    URL 时，倒计时类型自动转为 custom，保证与设置界面语义一致。

    当用户明确通过 --exam gaokao/zhongkao 选择预设倒计时模式时，自动
    启用壁纸和屏保——预设模式的核心用途就是显示倒计时，若此前用户
    关闭过壁纸（enabled=False），不自动启用会导致"选了中考却没壁纸"。
    """
    from . import config
    if "exam" in overrides:
        cfg["exam_type"] = overrides["exam"]
        if overrides["exam"] in ("gaokao", "zhongkao"):
            cfg["wallpaper"]["enabled"] = True
            cfg["screensaver"]["enabled"] = True
    config.resolve_exam(cfg)
    if "wallpaper_url" in overrides:
        cfg["wallpaper"]["url"] = overrides["wallpaper_url"]
        if "exam" not in overrides:
            cfg["exam_type"] = "custom"
    if "screensaver_url" in overrides:
        cfg["screensaver"]["url"] = overrides["screensaver_url"]
        if "exam" not in overrides:
            cfg["exam_type"] = "custom"
    if "wallpaper_enabled" in overrides:
        cfg["wallpaper"]["enabled"] = bool(overrides["wallpaper_enabled"])
    if "wallpaper_fit" in overrides:
        cfg["wallpaper"]["fit"] = overrides["wallpaper_fit"]
    if "wallpaper_mute" in overrides:
        cfg["wallpaper"]["mute"] = bool(overrides["wallpaper_mute"])
    if "screensaver_enabled" in overrides:
        cfg["screensaver"]["enabled"] = bool(overrides["screensaver_enabled"])
    if "screensaver_timeout" in overrides:
        cfg["screensaver"]["timeout"] = int(overrides["screensaver_timeout"])
    if "screensaver_fit" in overrides:
        cfg["screensaver"]["fit"] = overrides["screensaver_fit"]
    if "screensaver_mute" in overrides:
        cfg["screensaver"]["mute"] = bool(overrides["screensaver_mute"])
    if "video_loop" in overrides:
        cfg.setdefault("playback", {})["video_loop"] = bool(overrides["video_loop"])
    if "run_at_startup" in overrides:
        cfg["run_at_startup"] = bool(overrides["run_at_startup"])
    if "auto_check_update" in overrides:
        cfg["auto_check_update"] = bool(overrides["auto_check_update"])
    return cfg
