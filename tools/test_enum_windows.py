"""测试脚本：枚举所有窗口，打印句柄、进程ID、标题、样式，用于排查子窗口定位问题"""
import ctypes
from ctypes import wintypes
import sys, os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

current_pid = kernel32.GetCurrentProcessId()
print(f"当前进程 PID: {current_pid}")
print(f"Python: {sys.executable}")
print("=" * 80)

windows = []

def enum_callback(hwnd, lparam):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    visible = user32.IsWindowVisible(hwnd)

    # 获取标题
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    # 获取类名
    class_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_buf, 256)
    class_name = class_buf.value

    # 获取样式
    GWL_STYLE = -16
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)

    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_SYSMENU = 0x00080000

    windows.append({
        'hwnd': hwnd,
        'pid': pid.value,
        'visible': bool(visible),
        'title': title,
        'class': class_name,
        'style': style,
        'has_caption': bool(style & WS_CAPTION),
        'has_thickframe': bool(style & WS_THICKFRAME),
        'has_sysmenu': bool(style & WS_SYSMENU),
    })
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

print(f"\n共枚举到 {len(windows)} 个顶层窗口")
print("\n=== 当前进程的窗口 ===")
for w in windows:
    if w['pid'] == current_pid:
        print(f"  HWND={w['hwnd']:#x} visible={w['visible']}")
        print(f"    title='{w['title']}' class='{w['class']}'")
        print(f"    style={w['style']:#010x} caption={w['has_caption']} thickframe={w['has_thickframe']} sysmenu={w['has_sysmenu']}")
        print()

print("\n=== 所有可见窗口（前20个） ===")
visible_windows = [w for w in windows if w['visible']]
for w in visible_windows[:20]:
    marker = " <<< 当前进程" if w['pid'] == current_pid else ""
    print(f"  HWND={w['hwnd']:#x} PID={w['pid']:6d} title='{w['title'][:40]}' class='{w['class']}'{marker}")
