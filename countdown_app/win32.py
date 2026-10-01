# -*- coding: utf-8 -*-
"""Win32 API 封装（ctypes）：桌面结构定位与壁纸嵌入，参考 Lively Wallpaper。

关键经验（继承自旧版 HANDOFF 血泪史 + 本机探测验证）：
1. SendMessageTimeout(Progman, 0x052C, 0xD, 0x1) 才会创建壁纸 WorkerW（0,0 无效）
2. SetParent 前必须手动设 WS_CHILD（SetParent 不自动加）
3. 壁纸宿主 = 含 SHELLDLL_DefView 的 WorkerW 的下一个 WorkerW 兄弟；
   raised desktop（Win11，Progman 带 WS_EX_NOREDIRECTIONBITMAP）时宿主=Progman，
   且壁纸窗口需 WS_EX_LAYERED + alpha=255
4. 窗口操作必须与窗口创建同线程
5. SetWindowLongPtrW 的样式值需转有符号 32 位整数，否则 ctypes 溢出
"""
import ctypes
import os
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.SetParent.restype = wintypes.HWND
user32.GetParent.restype = wintypes.HWND
user32.GetWindowLongPtrW.restype = ctypes.c_long
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_long
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SendMessageTimeoutW.restype = ctypes.c_long
user32.SystemParametersInfoW.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.LPVOID,
                                         wintypes.DWORD]

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_POPUP = 0x80000000
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000
WS_EX_NOREDIRECTIONBITMAP = 0x00200000
LWA_ALPHA = 0x00000002
HWND_BOTTOM = 1
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SW_HIDE = 0
SW_SHOWNA = 8
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
WM_052C = 0x052C

SPI_GETDESKWALLPAPER = 0x0073
SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02
MAX_PATH_WALLPAPER = 520  # 长路径余量（宽字符）


def to_signed32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def set_process_dpi_awareness() -> None:
    """PerMonitorV2，必须在创建任何窗口前调用（否则窗口被缩放）。"""
    try:
        if not user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            user32.SetProcessDPIAware()
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def virtual_screen() -> tuple:
    """虚拟屏幕（跨显示器）几何：x, y, w, h。"""
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return int(x), int(y), int(w), int(h)


def find_progman():
    return user32.FindWindowW("Progman", None)


def send_spawn_workerw(progman) -> None:
    user32.SendMessageTimeoutW(progman, WM_052C, 0xD, 0x1, 0, 1000, None)


def is_raised_desktop(progman) -> bool:
    ex = user32.GetWindowLongPtrW(progman, GWL_EXSTYLE)
    return bool(ex & WS_EX_NOREDIRECTIONBITMAP)


def find_desktop_host() -> dict:
    """定位壁纸宿主窗口，兼容经典布局与 Win11 raised desktop。

    返回 {progman, host, raised}。
    """
    progman = find_progman()
    if not progman:
        raise RuntimeError("Progman not found")
    send_spawn_workerw(progman)
    raised = is_raised_desktop(progman)

    defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
    host = progman

    if not defview:
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lparam):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            if buf.value == "WorkerW":
                dv = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
                if dv:
                    found.append(hwnd)
                    return False
            return True

        user32.EnumWindows(cb, 0)
        if not found:
            raise RuntimeError("SHELLDLL_DefView not found")
        # Lively 同构：取 DefView 所在 WorkerW 的下一个 WorkerW 兄弟
        nxt = user32.FindWindowExW(None, found[0], "WorkerW", None)
        host = nxt if nxt else found[0]

    return {"progman": progman, "host": host, "raised": raised}


def make_child_window(hwnd) -> None:
    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    style = (style & ~WS_POPUP & ~WS_OVERLAPPEDWINDOW) | WS_CHILD | WS_VISIBLE
    user32.SetWindowLongPtrW(hwnd, GWL_STYLE, to_signed32(style))
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def set_ex_style(hwnd, add=0, remove=0) -> None:
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex = (ex | add) & ~remove
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, to_signed32(ex))


def attach_to_desktop(hwnd, host_info, x, y, w, h) -> None:
    """把窗口嵌入桌面壁纸层（壁纸窗口用，GUI 线程调用）。"""
    make_child_window(hwnd)
    raised = host_info["raised"]
    if raised:
        set_ex_style(hwnd, add=WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                     remove=WS_EX_APPWINDOW)
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
    else:
        set_ex_style(hwnd, add=WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                     remove=WS_EX_APPWINDOW | WS_EX_LAYERED)
    user32.SetParent(hwnd, host_info["host"])
    user32.SetWindowPos(hwnd, HWND_BOTTOM, x, y, w, h, SWP_NOACTIVATE)
    user32.ShowWindow(hwnd, SW_SHOWNA)


def topmost_fullscreen(hwnd, x, y, w, h) -> None:
    """屏保窗口用：全屏置顶。"""
    user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_SHOWWINDOW)


SW_SHOWMAXIMIZED = 3


def maximize(hwnd) -> None:
    """ShowWindow 最大化：系统按整显示器计算，可绕过工作区夹边。"""
    user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)


def is_window(hwnd) -> bool:
    return bool(user32.IsWindow(hwnd))


def last_input_idle_seconds() -> float:
    """距上次键鼠输入的秒数。"""

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    now = kernel32.GetTickCount()
    # GetTickCount 32 位回绕处理
    delta = (now - lii.dwTime) & 0xFFFFFFFF
    return delta / 1000.0


def set_autostart(enable: bool, exe_path: str) -> None:
    """HKCU Run 开机自启。"""
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Run",
                         0, winreg.KEY_SET_VALUE)
    try:
        if enable:
            winreg.SetValueEx(key, "CountdownDesktop", 0, winreg.REG_SZ,
                              '"%s"' % exe_path)
        else:
            try:
                winreg.DeleteValue(key, "CountdownDesktop")
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def get_desktop_wallpaper() -> str:
    """读当前桌面壁纸文件路径（SPI_GETDESKWALLPAPER）。

    返回空串表示获取失败。注册表可能指向 TranscodedWallpaper（无扩展名的
    JPEG），SPI 返回的就是它，原样存回即可。
    """
    buf = ctypes.create_unicode_buffer(MAX_PATH_WALLPAPER)
    ok = user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, MAX_PATH_WALLPAPER,
                                      buf, 0)
    return buf.value if ok else ""


def set_desktop_wallpaper(path: str) -> bool:
    """强制 explorer 重设壁纸（SPI_SETDESKWALLPAPER）。

    播放器退出后 explorer 不会自动重绘壁纸层（用户看到白屏），
    重设一次即恢复。路径为空/文件不存在时返回 False（由调用方兜底）。
    """
    if not path:
        return False
    p = os.path.expandvars(path)
    if not os.path.isfile(p):
        # 不提前拦截：TranscodedWallpaper 可能被系统重建，交给 SPI 校验
        log.warning("wallpaper file missing, still trying SPI_SET: %s", p)
    ok = user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, p,
                                      SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
    if not ok:
        log.warning("SPI_SETDESKWALLPAPER failed (path=%s, err=%s)",
                    p, kernel32.GetLastError())
    return bool(ok)


def refresh_desktop_wallpaper() -> bool:
    """把当前壁纸原样重设一次，强制 explorer 重绘壁纸层。

    本软件从不修改系统壁纸值（只叠加窗口），因此无需快照：
    直接重设 SPI 当前值即可恢复显示，也不会回滚用户中途更换的壁纸。
    """
    cur = get_desktop_wallpaper()
    if not cur:
        log.warning("no current wallpaper to refresh")
        return False
    return set_desktop_wallpaper(cur)


def create_single_instance_mutex(name: str):
    """返回 mutex 句柄；若已存在实例返回 None。"""
    handle = kernel32.CreateMutexW(None, False, name)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return None
    return handle


def system_uses_light_theme() -> bool:
    r"""读取 Windows 个性化设置：应用主题是否为浅色。

    注册表 HKCU\...\Themes\Personalize\AppsUseLightTheme：1=浅色，0=深色。
    键不存在（老系统/未设置）时默认深色 → 托盘用白色 glyph。
    """
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            0, winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return bool(int(val))
        finally:
            winreg.CloseKey(key)
    except (OSError, ValueError, TypeError):
        return False
