#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""早读班级配置的读写（不依赖 PySide6，供 core / 后端 / 悬浮球 / 浏览器共用）。

历史问题：core.py 和 morning_browser.py 各写了一份加解密和路径常量，
改动一处另一处就不同步；而且 "非持久登录" 的 persistent 参数在后端调用时被丢掉，
导致勾掉"记住登录"也会把密码写进 D 盘。这里统一收口。
"""
from __future__ import annotations

import base64
import json
import os
import tempfile

# 与后端保持一致的数据目录（冰点还原不影响 D 盘）
DATA_DIR = os.environ.get("IDIOT_LAUNCH_DATA", r"D:\IdiotLaunch\data")
PERSISTENT_CONFIG_PATH = os.path.join(DATA_DIR, "morning_config.json")
TEMP_CONFIG_PATH = os.path.join(
    os.environ.get("TEMP", tempfile.gettempdir()), "idiot_launch_morning_config.json"
)

MORNING_READING_URL = "https://zztool.free.nf/morning-reading"
MORNING_API_URL = "https://zztool.free.nf/morning-reading/api.php"

# 说明：这只是"避免明文"，不是强加密。D 盘上同机器任何账号都能读到，
# 设置页已如实告知用户。密钥变更会导致旧配置解不开，因此不要随意修改。
_PASSWORD_KEY = b"IdiotLaunch_Morning_Reading_2024"


def encrypt_password(password: str) -> str:
    if not password:
        return ""
    data = password.encode("utf-8")
    enc = bytes(data[i] ^ _PASSWORD_KEY[i % len(_PASSWORD_KEY)] for i in range(len(data)))
    return "enc:" + base64.b64encode(enc).decode("ascii")


def decrypt_password(encrypted: str) -> str:
    """解密；旧版本的明文配置直接返回。

    解密失败返回空串（而不是把密文当密码用，避免"密码错误"这种查不出原因的报错）。
    """
    if not encrypted:
        return ""
    if not encrypted.startswith("enc:"):
        return encrypted
    try:
        data = base64.b64decode(encrypted[4:])
        return bytes(
            data[i] ^ _PASSWORD_KEY[i % len(_PASSWORD_KEY)] for i in range(len(data))
        ).decode("utf-8")
    except Exception:
        return ""


def paths() -> tuple[str, str]:
    return TEMP_CONFIG_PATH, PERSISTENT_CONFIG_PATH


def load() -> dict:
    """优先临时配置（非持久登录），其次持久配置。密码已解密。"""
    for path in (TEMP_CONFIG_PATH, PERSISTENT_CONFIG_PATH):
        try:
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                continue
            if "password" in cfg:
                cfg["password"] = decrypt_password(str(cfg.get("password", "")))
            return cfg
        except Exception:
            continue
    return {}


def save(config: dict, persistent: bool = True) -> bool:
    """保存配置。persistent=False 写临时文件（重启后失效）。

    原子写入：先写 .tmp 再替换，避免断电/并发写出半个 JSON。
    """
    path = PERSISTENT_CONFIG_PATH if persistent else TEMP_CONFIG_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cfg = dict(config)
        cfg["persistent"] = bool(persistent)
        if cfg.get("password"):
            cfg["password"] = encrypt_password(str(cfg["password"]))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        if persistent and os.path.isfile(TEMP_CONFIG_PATH):
            try:
                os.remove(TEMP_CONFIG_PATH)
            except OSError:
                pass
        if not persistent:
            # 改成非持久登录时，把之前的持久配置也删掉，否则下次会被读回来
            try:
                if os.path.isfile(PERSISTENT_CONFIG_PATH):
                    os.remove(PERSISTENT_CONFIG_PATH)
            except OSError:
                pass
        return True
    except Exception:
        return False


def clear_temp() -> None:
    try:
        if os.path.isfile(TEMP_CONFIG_PATH):
            os.remove(TEMP_CONFIG_PATH)
    except OSError:
        pass


def clear_all() -> None:
    for path in (TEMP_CONFIG_PATH, PERSISTENT_CONFIG_PATH):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
