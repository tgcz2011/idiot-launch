#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 PE 版本元数据（version_info.txt）。

用法: python tools/gen_version_info.py <version> [exe名] [产品名] [输出路径]
例:   python tools/gen_version_info.py 3.0.0.0-beta27
      python tools/gen_version_info.py 3.0.0.0-beta27 IdiotLaunchBackend.exe \
            "傻瓜启动器后端" dist/backend_version_info.txt
"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_content(version: str, exe_name: str, product: str) -> str:
    # Windows 文件版本只接受 4 段数字，beta/alpha 后缀去掉
    parts = []
    for p in version.split(".")[:4]:
        m = re.match(r"(\d+)", p)
        parts.append(m.group(1) if m else "0")
    while len(parts) < 4:
        parts.append("0")
    vt = "({}, {}, {}, {})".format(*parts[:4])
    return f"""# -*- mode: python ; coding: utf-8 -*-
# 本文件由 tools/gen_version_info.py 自动生成，请勿手工修改
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vt},
    prodvers={vt},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'080404B0',
        [StringStruct(u'CompanyName', u'tgcz2011'),
        StringStruct(u'FileDescription', u'{product}'),
        StringStruct(u'FileVersion', u'{version}'),
        StringStruct(u'InternalName', u'{os.path.splitext(exe_name)[0]}'),
        StringStruct(u'LegalCopyright', u'Copyright (C) 2026 tgcz2011'),
        StringStruct(u'OriginalFilename', u'{exe_name}'),
        StringStruct(u'ProductName', u'{product}'),
        StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [0x0804, 0x04B0])])
  ]
)
"""


def generate(version: str, exe_name: str = "IdiotLaunch.exe",
             product: str = "傻瓜启动器", out_path: str | None = None) -> str:
    out_path = out_path or os.path.join(PROJECT_ROOT, "version_info.txt")
    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(build_content(version, exe_name, product))
    return out_path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    version = sys.argv[1]
    exe_name = sys.argv[2] if len(sys.argv) > 2 else "IdiotLaunch.exe"
    product = sys.argv[3] if len(sys.argv) > 3 else "傻瓜启动器"
    out_path = sys.argv[4] if len(sys.argv) > 4 else None
    path = generate(version, exe_name, product, out_path)
    print(f"已生成 {path} (v{version})")


if __name__ == "__main__":
    main()
