#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""工具脚本的控制台兼容层。

背景：这些脚本会打印中文。中文 Windows 的控制台是 GBK，GitHub Actions 的
Windows runner 是 cp1252 —— 两者都编不出中文/✓✗ 这类字符，
`print()` 会直接抛 UnicodeEncodeError 把整个步骤打成失败
（真实事故：CI 在"生成 PE 元数据"这步挂掉，本地 bump_version 只改了一半版本号）。

用法：脚本开头
    from _console import setup_console
    setup_console()
"""
import sys


def setup_console() -> None:
    """把 stdout/stderr 切到 UTF-8，并且永不因为编码问题抛异常。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
