# -*- coding: utf-8 -*-
"""播放器进程：渲染壁纸/屏保网页窗口。

架构参考 Lively（主程序 + 独立播放器进程）：
- mode=wallpaper: 窗口嵌入桌面壁纸层（WorkerW/Progman），随主程序常驻
- mode=screensaver: 全屏置顶自绘窗口，任意键鼠输入即退出（不用系统屏保）

渲染引擎：pywebview EdgeChromium(WebView2)。已验证 SetParent 后渲染正常
（QtWebEngine 在 reparent 后渲染停止，旧版因此失败的教训）。
"""
import ctypes
import logging
import os
import sys
import threading
import time
from ctypes import wintypes

log = logging.getLogger("player")


def _setup_webview2_audio_policy(mute: bool) -> None:
    """按配置设置 WebView2 音频策略（网页与视频统一生效）。

    - 放行带声音自动播放：--autoplay-policy=no-user-gesture-required
    - mute=True：追加 --mute-audio（网页源也静音，<video muted> 管不到网页）
    必须在 WebView2 Environment 创建前（webview.start 之前）设置，
    只影响本进程新创建的 Environment；已有参数合并去重，不抢占外部预设。
    """
    want = ["--autoplay-policy=no-user-gesture-required"]
    if mute:
        want.append("--mute-audio")
    existing = (os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS") or "").split()
    merged = existing + [a for a in want if a not in existing]
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = " ".join(merged)

WINDOW_TITLE = {"wallpaper": "CountdownWallpaper", "screensaver": "CountdownScreensaver"}


def _setup_logging(mode: str) -> None:
    from . import config
    path = os.path.join(config.config_dir(), "player-%s.log" % mode)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        filename=path,
        encoding="utf-8",
    )


def _find_own_window(title: str):
    from . import win32
    mypid = os.getpid()
    found = [0]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        pid = wintypes.DWORD()
        win32.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == mypid:
            buf = ctypes.create_unicode_buffer(512)
            win32.user32.GetWindowTextW(hwnd, buf, 512)
            if buf.value == title:
                found[0] = hwnd
                return False
        return True

    win32.user32.EnumWindows(cb, 0)
    return found[0]


def run(mode: str) -> None:
    _setup_logging(mode)
    from . import config, win32, media, cli
    import webview

    win32.set_process_dpi_awareness()
    cfg = config.load()
    # CLI 覆盖只改内存，不落盘（主进程已透传同一组参数）
    cli.apply(cli.parse_argv(sys.argv)[0], cfg)
    title = WINDOW_TITLE[mode]
    url = cfg[mode]["url"]
    fit = cfg[mode].get("fit", "cover")
    mute = bool(cfg[mode].get("mute", True))
    # 环境变量必须在 webview.start 之前、按本模式配置设置
    _setup_webview2_audio_policy(mute)
    loop = bool(cfg.get("playback", {}).get("video_loop", True))
    x, y, w, h = win32.virtual_screen()

    kind, src, local = media.resolve(url)
    if local is not None:
        _KEEP_LOCAL[mode] = local
    log.info("starting player mode=%s url=%s kind=%s fit=%s mute=%s loop=%s rect=%s",
             mode, url, kind, fit, mute, loop, (x, y, w, h))

    html = (media.build_html(kind, src, fit=fit, mute=mute, loop=loop)
            if kind in ("video", "anim", "image") else None)
    window = webview.create_window(
        title, src if html is None else "", html=html,
        width=w, height=h, x=x, y=y, frameless=True)

    def on_shown():
        try:
            _on_shown(mode, window)
        except Exception:
            log.exception("on_shown failed")

    window.events.shown += on_shown
    window.events.closed += lambda: _on_closed(mode)

    webview.start(gui="edgechromium", private_mode=False)
    # webview.start 正常返回（优雅退出）时 closed 事件可能不触发，补一次兑底
    _on_closed(mode)
    log.info("player loop exited mode=%s", mode)


def _on_closed(mode: str) -> None:
    """播放器优雅退出时的兑底重绘（主进程 terminate 杀进程时不会走到这里，
    由主进程 stop_wallpaper 后统一 refresh）。"""
    if mode != "wallpaper":
        return
    try:
        from . import win32
        if win32.refresh_desktop_wallpaper():
            log.info("desktop wallpaper refreshed on player exit")
    except Exception:
        log.exception("refresh wallpaper failed")


_KEEP_LOCAL = {}


def _on_shown(mode: str, window) -> None:
    from . import win32
    time.sleep(0.3)
    hwnd = _find_own_window(WINDOW_TITLE[mode])
    if not hwnd:
        log.error("own window not found")
        window.destroy()
        return
    x, y, w, h = win32.virtual_screen()

    if mode == "wallpaper":
        host_info = win32.find_desktop_host()
        log.info("host=0x%x raised=%s", host_info["host"], host_info["raised"])
        win32.attach_to_desktop(hwnd, host_info, x, y, w, h)
        log.info("wallpaper attached")
    else:
        # 屏保：全屏置顶 + 隐藏光标与任务栏 + 输入监听退出
        win32.set_ex_style(hwnd, add=win32.WS_EX_TOOLWINDOW | win32.WS_EX_NOACTIVATE,
                           remove=win32.WS_EX_APPWINDOW)
        _hide_taskbar(True)
        # 先隐藏任务栏再 maximize：最大化按整显示器计算，绕过工作区夹边；
        # SetWindowPos 单独用会被 Qt 夹到工作区附近尺寸（实测 3824x1707 vs 3840x1746）
        win32.maximize(hwnd)
        win32.topmost_fullscreen(hwnd, x, y, w, h)
        win32.user32.ShowCursor(False)
        log.info("screensaver shown")

        def watch_input():
            time.sleep(1.0)  # 启动瞬间的输入不触发退出
            while True:
                if win32.last_input_idle_seconds() < 0.5:
                    log.info("user input detected, exiting screensaver")
                    break
                time.sleep(0.2)
            _hide_taskbar(False)
            win32.user32.ShowCursor(True)
            window.destroy()

        threading.Thread(target=watch_input, daemon=True).start()


def _hide_taskbar(hide: bool) -> None:
    from . import win32
    tray = win32.user32.FindWindowW("Shell_TrayWnd", None)
    if tray:
        win32.user32.ShowWindow(tray, win32.SW_HIDE if hide else 5)  # 5=SW_SHOW


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "wallpaper")
