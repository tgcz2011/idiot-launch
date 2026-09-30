#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 version_info.txt（PE 元数据），避免 PowerShell here-string 中文编码问题。
用法: python gen_version_info.py <version> <app_name> <file_description>
"""
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: python gen_version_info.py <version> [app_name] [file_description]")
        sys.exit(1)
    version = sys.argv[1]
    app_name = sys.argv[2] if len(sys.argv) > 2 else "Idiot Launch"
    file_desc = sys.argv[3] if len(sys.argv) > 3 else "Idiot Launch"
    internal_name = app_name.replace(" ", "")
    parts = version.split(".")
    vt = f"({parts[0]}, {parts[1]}, {parts[2]}, {parts[3]})"
    content = f"""# -*- mode: python ; coding: utf-8 -*-
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
        StringStruct(u'FileDescription', u'{file_desc}'),
        StringStruct(u'FileVersion', u'{version}'),
        StringStruct(u'InternalName', u'{internal_name}'),
        StringStruct(u'LegalCopyright', u'Copyright (C) 2026 tgcz2011'),
        StringStruct(u'OriginalFilename', u'{internal_name}.exe'),
        StringStruct(u'ProductName', u'{app_name}'),
        StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [0x0804, 0x04B0])])
  ]
)
"""
    with open("version_info.txt", "w", encoding="utf-8") as f:
        f.write(content)
    print(f"version_info.txt synced to {version}")


if __name__ == "__main__":
    main()
