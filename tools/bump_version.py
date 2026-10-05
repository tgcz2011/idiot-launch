#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""版本号同步：一处填写，四处落盘。

用法: python tools/bump_version.py 3.0.0.0-beta27

会更新：
  1. src/core.py            LAUNCHER_VERSION（唯一真源）
  2. IdiotLaunch.iss        MyAppVersion（安装包文件名/版本）
  3. flutter_app/pubspec.yaml  version（Flutter 产物版本）
  4. version_info.txt / version_info_backend.txt（PE 元数据）
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _console import setup_console  # noqa: E402

# 中文 Windows 控制台默认 GBK，CI 的 Windows runner 是 cp1252：
# 输出中文或 ✓/✗ 会直接抛 UnicodeEncodeError，脚本跑到一半就中断。
setup_console()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)(?:-(beta|alpha|rc)(\d+))?$")


def sync_version(version: str) -> bool:
    m = VERSION_RE.match(version)
    if not m:
        print(f"错误: 版本号格式不正确: {version}")
        print("正确格式: 3.0.0.0 或 3.0.0.0-beta27")
        return False
    major, minor, patch, build, pre_kind, pre_num = m.groups()
    # beta 用 beta 号当 Flutter 的 build number；正式版用第 4 位。
    # 正式版第 4 位是 0（如 3.0.0.0）时写成 +0 会被一些工具当成"没设置"，所以至少给 1。
    build_num = pre_num if pre_kind else (build if int(build) > 0 else "1")
    pubspec_version = f"{major}.{minor}.{patch}+{build_num}"

    targets = [
        (os.path.join(PROJECT_ROOT, "src", "core.py"),
         r'LAUNCHER_VERSION\s*=\s*"[^"]+"', f'LAUNCHER_VERSION = "{version}"'),
        (os.path.join(PROJECT_ROOT, "IdiotLaunch.iss"),
         r'#define MyAppVersion "[^"]+"', f'#define MyAppVersion "{version}"'),
        (os.path.join(PROJECT_ROOT, "flutter_app", "pubspec.yaml"),
         r'^version:\s*.+$', f'version: {pubspec_version}'),
    ]
    for path, pattern, repl in targets:
        if not os.path.isfile(path):
            print(f"  [skip] 文件不存在: {path}")
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        new_content, n = re.subn(pattern, repl, content, flags=re.MULTILINE)
        if n == 0:
            print(f"  [warn] 未匹配到版本号: {path}")
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  [ok] {os.path.relpath(path, PROJECT_ROOT)}")

    from gen_version_info import generate

    generate(version, "IdiotLaunch.exe", "傻瓜启动器",
             os.path.join(PROJECT_ROOT, "version_info.txt"))
    generate(version, "IdiotLaunchBackend.exe", "傻瓜启动器后端",
             os.path.join(PROJECT_ROOT, "version_info_backend.txt"))
    print("  [ok] version_info.txt / version_info_backend.txt")

    print(f"\n版本号已同步为 {version}")
    print("下一步：")
    print(f'  git add -A && git commit -m "chore: 升版本号到 {version}"')
    print(f"  git tag v{version} && git push origin main v{version}")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(0 if sync_version(sys.argv[1]) else 1)
