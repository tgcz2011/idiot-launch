"""真实跑一遍"检查更新"，把每个渠道的结果都打出来。

用法（在仓库根目录）：
    python tools/check_update.py                 # 按当前版本查
    python tools/check_update.py --as 3.0.0.0-beta29   # 假装自己是旧版本

为什么需要它：更新检查曾经因为 `Accept: application/vnd.github+json`
被 Supabase 判 406、GitHub 兜底又用着构建时塞进去的临时 token，
静默失败了很久，界面还一直显示"当前已是最新版本"。
出问题时先跑这个脚本，再去看 `data\\daemon.log`。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from tools._console import setup_console
except ImportError:  # 直接 python tools/check_update.py 时包路径不同
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _console import setup_console

setup_console()

import src.core as core  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="检查更新（含各渠道诊断）")
    parser.add_argument("--as", dest="fake_version", default="",
                        help="假装当前是这个版本，用来验证旧版本能不能看到更新")
    args = parser.parse_args()

    print(f"仓库里的版本号: {core.LAUNCHER_VERSION}")
    if args.fake_version:
        core.LAUNCHER_VERSION = args.fake_version
        print(f"本次按这个版本查: {args.fake_version}")

    if not core.GITHUB_TOKEN:
        print("GitHub token: 空（走未认证，60 次/小时；这是正常的）")
    else:
        print(f"GitHub token: 有（{len(core.GITHUB_TOKEN)} 字符）")

    info = core.get_latest_launcher_info()
    check = core.last_check_result()

    print("\n--- 结论 ---")
    ok = check.get("ok")
    if info:
        print(f"有新版本: {info['version']}")
        print(f"  下载地址: {info['url']}")
        print(f"  SHA-256 : {info['sha256'] or '（渠道没给，下载后会跳过校验）'}")
    elif ok:
        print(f"已是最新（{check.get('detail')}）")
    elif ok is False:
        print(f"没查成（{check.get('detail')}）—— 界面会如实显示「检查更新失败」")
    else:
        print("没有结论（不应该出现，请检查代码）")

    if info:
        print("\n发布说明前 200 字：")
        print((info.get("release_notes") or "").replace("\r\n", "\n")[:200])

    print("\n各渠道的失败原因（如果有）请看 data\\daemon.log 的最后几行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
