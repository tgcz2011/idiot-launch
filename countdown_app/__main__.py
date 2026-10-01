# -*- coding: utf-8 -*-
"""python -m countdown_app 入口。
无参数=主程序（托盘+设置），player <mode>=播放器进程。
"""
import sys

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "player":
        mode = "wallpaper"
        for a in args[1:]:
            if not a.startswith("-"):
                mode = a
                break
        from . import player
        player.run(mode)
    else:
        from . import main
        sys.exit(main.run())
