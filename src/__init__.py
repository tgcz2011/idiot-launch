"""
Idiot Launch — 傻瓜式启动器
专为学校电脑设计：一键启动中考/高考倒计时（Countdown Desktop），或打开早晚读网页。
自动检测 Countdown Desktop 是否安装，未安装则静默安装到 D 盘（规避冰点还原 C 盘重置）。
"""
import sys
import os


def resource_path(relative: str) -> str:
    """获取打包后资源的绝对路径（兼容 PyInstaller onefile/onedir 与开发模式）。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)
