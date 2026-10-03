#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
版本号同步脚本：自动同步 core.py / IdiotLaunch.iss / pubspec.yaml 三处版本号。
用法: python tools/bump_version.py 3.0.0.0-beta20
"""
import sys
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sync_version(version: str):
    """同步版本号到三个文件。"""
    # 解析版本号
    # 格式: a.b.c.d 或 a.b.c.d-betaN
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)\.(\d+)(?:-(beta\d+|alpha\d+|rc\d+))?$', version)
    if not m:
        print(f"错误: 版本号格式不正确: {version}")
        print("正确格式: 3.0.0.0 或 3.0.0.0-beta20")
        return False

    major, minor, patch, build, pre = m.groups()
    full_version = version
    # pubspec 格式: 3.0.0+20 (beta 版本用 beta 后的数字作为 build number)
    if pre:
        # 提取 beta/alpha/rc 后的数字
        pre_num = re.search(r'\d+', pre)
        build_num = pre_num.group() if pre_num else build
    else:
        build_num = build
    pubspec_version = f"{major}.{minor}.{patch}+{build_num}"

    print(f"同步版本号: {full_version}")
    print(f"  core.py LAUNCHER_VERSION = {full_version}")
    print(f"  IdiotLaunch.iss MyAppVersion = {full_version}")
    print(f"  pubspec.yaml version = {pubspec_version}")

    # 1. core.py
    core_path = os.path.join(PROJECT_ROOT, "src", "core.py")
    with open(core_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r'LAUNCHER_VERSION\s*=\s*"[^"]+"',
        f'LAUNCHER_VERSION = "{full_version}"',
        content
    )
    with open(core_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✓ core.py 已更新")

    # 2. IdiotLaunch.iss
    iss_path = os.path.join(PROJECT_ROOT, "IdiotLaunch.iss")
    if os.path.isfile(iss_path):
        with open(iss_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(
            r'#define MyAppVersion "[^"]+"',
            f'#define MyAppVersion "{full_version}"',
            content
        )
        with open(iss_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  ✓ IdiotLaunch.iss 已更新")

    # 3. pubspec.yaml
    pubspec_path = os.path.join(PROJECT_ROOT, "flutter_app", "pubspec.yaml")
    with open(pubspec_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r'^version:\s*.+$',
        f'version: {pubspec_version}',
        content,
        flags=re.MULTILINE
    )
    with open(pubspec_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✓ pubspec.yaml 已更新")

    print(f"\n版本号同步完成: {full_version}")
    print("下一步: git add -A && git commit -m '版本号升级到 v{full_version}' && git tag v{full_version} && git push --tags")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python tools/bump_version.py <版本号>")
        print("示例: python tools/bump_version.py 3.0.0.0-beta20")
        sys.exit(1)
    sync_version(sys.argv[1])
