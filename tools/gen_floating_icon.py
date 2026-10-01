# -*- coding: utf-8 -*-
"""从 icon.ico 生成悬浮球专用 PNG 图标。"""
import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ico_path = os.path.join(ROOT, "assets", "icon.ico")

# ICO 打开默认取最大尺寸帧
ico = Image.open(ico_path)
print("ico size:", ico.size, ico.mode)
img = ico.convert("RGBA")

img48 = img.resize((48, 48), Image.LANCZOS)
img48.save(os.path.join(ROOT, "assets", "floating_icon.png"))
print("saved assets/floating_icon.png", img48.size)

img64 = img.resize((64, 64), Image.LANCZOS)
img64.save(os.path.join(ROOT, "assets", "floating_icon_64.png"))
print("saved assets/floating_icon_64.png", img64.size)
