#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
morning-reading API 自动客户端（纯 Python 标准库，零依赖）

解决的问题：InfinityFree 免费托管会对"非浏览器"请求注入 JS 挑战页
（slowAES 加密一个 __test cookie，浏览器执行 JS 后自动通过）。
本客户端内嵌 AES-128 解密，自动完成挑战，调用方无需关心任何挑战细节，
也不需要 openssl / Node / pip 包。

速度设计（与"直接调 API"几乎无差别）：
- token 缓存：同一小时槽内的 token 复用（内存 + ~/.morning_reading_api_cache.json 文件），
  不重复调 get_seed，普通调用只有 1 次 HTTP 往返；
- 挑战 cookie 缓存：__test 有效期 6 小时，落盘后同机复用，不会每次重新过挑战；
- 自动恢复：token 跨小时轮换（±1 小时窗口）时，遇到 401 自动重新取种子算 token 重试；
  挑战 cookie 过期时，请求会拿到挑战页，客户端自动解密重试——都无需调用方干预。

用法示例：
    python3 api_client.py --identity teacher --user 9-6 --pass 教师密码 verify_token
    python3 api_client.py --identity teacher --user 9-6 --pass 教师密码 students
    python3 api_client.py --identity record  --user 9-6 --pass 班级密码 stats --period week
    python3 api_client.py --identity record  --user 9-6 --pass 班级密码 add_record --student-no 1
    python3 api_client.py --identity superadmin --user superadmin --pass 总密码 status --grade-class 9-6

认证流程（与教师管理页文档一致）：
    1) GET action=get_seed&identity=<身份>  （无需登录，自动过挑战）
    2) token = sha256(用户名 : 密码 : 种子)
    3) 请求带 ?token=<token>（等价于 Authorization: Bearer）
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

DEFAULT_BASE = "http://zztool.free.nf/morning-reading/api.php"
CACHE_FILE = os.path.join(os.path.expanduser("~"), ".morning_reading_api_cache.json")
_TOKEN_MAX_AGE = 7200      # token 缓存最长 2 小时（跨小时 ±1 窗口足够）
_COOKIE_MAX_AGE = 21600    # InfinityFree 挑战 cookie 有效期 6 小时

# ---------- InfinityFree 挑战密钥（挑战页明文公开，非项目机密） ----------
_CHAL_KEY_HEX = "f655ba9d09a112d4968c63579db590b4"
_CHAL_IV_HEX = "98344c2eee86c3994890592585b49f80"
_UA = "Mozilla/5.0"


# ---------- 纯 Python AES-128 解密（仅用于解挑战 cookie） ----------
_SBOX = [
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
]
_INV_SBOX = [
    0x52,0x09,0x6a,0xd5,0x30,0x36,0xa5,0x38,0xbf,0x40,0xa3,0x9e,0x81,0xf3,0xd7,0xfb,
    0x7c,0xe3,0x39,0x82,0x9b,0x2f,0xff,0x87,0x34,0x8e,0x43,0x44,0xc4,0xde,0xe9,0xcb,
    0x54,0x7b,0x94,0x32,0xa6,0xc2,0x23,0x3d,0xee,0x4c,0x95,0x0b,0x42,0xfa,0xc3,0x4e,
    0x08,0x2e,0xa1,0x66,0x28,0xd9,0x24,0xb2,0x76,0x5b,0xa2,0x49,0x6d,0x8b,0xd1,0x25,
    0x72,0xf8,0xf6,0x64,0x86,0x68,0x98,0x16,0xd4,0xa4,0x5c,0xcc,0x5d,0x65,0xb6,0x92,
    0x6c,0x70,0x48,0x50,0xfd,0xed,0xb9,0xda,0x5e,0x15,0x46,0x57,0xa7,0x8d,0x9d,0x84,
    0x90,0xd8,0xab,0x00,0x8c,0xbc,0xd3,0x0a,0xf7,0xe4,0x58,0x05,0xb8,0xb3,0x45,0x06,
    0xd0,0x2c,0x1e,0x8f,0xca,0x3f,0x0f,0x02,0xc1,0xaf,0xbd,0x03,0x01,0x13,0x8a,0x6b,
    0x3a,0x91,0x11,0x41,0x4f,0x67,0xdc,0xea,0x97,0xf2,0xcf,0xce,0xf0,0xb4,0xe6,0x73,
    0x96,0xac,0x74,0x22,0xe7,0xad,0x35,0x85,0xe2,0xf9,0x37,0xe8,0x1c,0x75,0xdf,0x6e,
    0x47,0xf1,0x1a,0x71,0x1d,0x29,0xc5,0x89,0x6f,0xb7,0x62,0x0e,0xaa,0x18,0xbe,0x1b,
    0xfc,0x56,0x3e,0x4b,0xc6,0xd2,0x79,0x20,0x9a,0xdb,0xc0,0xfe,0x78,0xcd,0x5a,0xf4,
    0x1f,0xdd,0xa8,0x33,0x88,0x07,0xc7,0x31,0xb1,0x12,0x10,0x59,0x27,0x80,0xec,0x5f,
    0x60,0x51,0x7f,0xa9,0x19,0xb5,0x4a,0x0d,0x2d,0xe5,0x7a,0x9f,0x93,0xc9,0x9c,0xef,
    0xa0,0xe0,0x3b,0x4d,0xae,0x2a,0xf5,0xb0,0xc8,0xeb,0xbb,0x3c,0x83,0x53,0x99,0x61,
    0x17,0x2b,0x04,0x7e,0xba,0x77,0xd6,0x26,0xe1,0x69,0x14,0x63,0x55,0x21,0x0c,0x7d,
]
_RCON = [0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _xtime(a):
    return ((a << 1) ^ (0x1b if a & 0x80 else 0)) & 0xFF


def _gmul(a, b):
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        b >>= 1
        a = _xtime(a)
    return r


def _inv_mix_column(col):
    a0, a1, a2, a3 = col
    return [
        _gmul(a0, 0x0e) ^ _gmul(a1, 0x0b) ^ _gmul(a2, 0x0d) ^ _gmul(a3, 0x09),
        _gmul(a0, 0x09) ^ _gmul(a1, 0x0e) ^ _gmul(a2, 0x0b) ^ _gmul(a3, 0x0d),
        _gmul(a0, 0x0d) ^ _gmul(a1, 0x09) ^ _gmul(a2, 0x0e) ^ _gmul(a3, 0x0b),
        _gmul(a0, 0x0b) ^ _gmul(a1, 0x0d) ^ _gmul(a2, 0x09) ^ _gmul(a3, 0x0e),
    ]


def _key_expansion(key):
    w = [int.from_bytes(key[i:i + 4], "big") for i in range(0, 16, 4)]
    for i in range(4, 44):
        t = w[i - 1]
        if i % 4 == 0:
            t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF  # RotWord
            t = ((_SBOX[(t >> 24) & 0xFF] << 24)
                 | (_SBOX[(t >> 16) & 0xFF] << 16)
                 | (_SBOX[(t >> 8) & 0xFF] << 8)
                 | _SBOX[t & 0xFF]) ^ (_RCON[i // 4] << 24)  # SubWord + Rcon
        w.append(w[i - 4] ^ t)
    return w


def aes128_decrypt_block(cipher: bytes, key: bytes) -> bytes:
    """AES-128 单块解密（无填充处理，供挑战 cookie 使用）。"""
    state = [[cipher[4 * j + i] for j in range(4)] for i in range(4)]  # 列主序
    words = _key_expansion(key)
    rk = [[words[r * 4 + c] for c in range(4)] for r in range(11)]  # 每轮 4 个 word

    def add_rk(round_no):
        for c in range(4):
            word = rk[round_no][c]
            state[0][c] ^= (word >> 24) & 0xFF
            state[1][c] ^= (word >> 16) & 0xFF
            state[2][c] ^= (word >> 8) & 0xFF
            state[3][c] ^= word & 0xFF

    def inv_shift_rows():
        for r in range(1, 4):
            state[r] = state[r][-r:] + state[r][:-r]  # 解密：右移 r

    def inv_sub_bytes():
        for i in range(4):
            for j in range(4):
                state[i][j] = _INV_SBOX[state[i][j]]

    def inv_mix_columns():
        for c in range(4):
            col = [state[i][c] for i in range(4)]
            mixed = _inv_mix_column(col)
            for i in range(4):
                state[i][c] = mixed[i]

    add_rk(10)
    for r in range(9, 0, -1):
        inv_shift_rows()
        inv_sub_bytes()
        add_rk(r)
        inv_mix_columns()
    inv_shift_rows()
    inv_sub_bytes()
    add_rk(0)
    return bytes(state[i][j] for j in range(4) for i in range(4))


def _solve_challenge_cookie(html: str):
    """从挑战页提取并解出 __test cookie 值；非挑战页返回 None。"""
    m = re.search(r'c=toNumbers\("([0-9a-f]{32,})"\)', html)
    if not m:
        return None
    c = bytes.fromhex(m.group(1))
    key = bytes.fromhex(_CHAL_KEY_HEX)
    iv = bytes.fromhex(_CHAL_IV_HEX)
    plain = aes128_decrypt_block(c, key)
    first = bytes(a ^ b for a, b in zip(plain, iv))  # CBC：第一块 XOR IV
    return first.hex()


# ---------- 本地缓存（token / 挑战 cookie 落盘，同机复用） ----------
def _load_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass  # 缓存写失败不影响功能


# ---------- 自动过挑战的 HTTP 会话 ----------
class ApiSession:
    def __init__(self, base: str, use_file_cache: bool = True):
        self.base = base
        self.cookie = None
        self.cache = _load_cache() if use_file_cache else {}
        c = self.cache.get("cookie")
        if c and c.get("value") and c.get("expires_ts", 0) > time.time():
            self.cookie = c["value"]

    def _open(self, url: str, data: bytes | None = None) -> str:
        req = urllib.request.Request(url, data=data, headers={
            "User-Agent": _UA,
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded" if data else "text/plain;charset=UTF-8",
        })
        if self.cookie:
            req.add_header("Cookie", f"__test={self.cookie}")
        try:
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            # 401/403（token 无效、权限不足）与 400（POST 遇挑战）都带可读 body，
            # 读出来交给上层处理（401 重试 / 挑战页自动解密 / 业务错误）
            return e.read().decode("utf-8", "replace")

    def request(self, url: str, data: bytes | None = None) -> str:
        """带参数请求，自动处理挑战；返回服务端真实响应文本。

        挑战 cookie 过期/丢失时，服务器会返回挑战页 → 自动解密新 cookie →
        带 cookie 重访（附加 i=1）。循环最多 3 次，之后仍失败则报错。
        """
        for attempt in range(3):
            body = self._open(url, data)
            cookie = _solve_challenge_cookie(body)
            if cookie is None:
                return body
            self.cookie = cookie
            self.cache["cookie"] = {"value": cookie, "expires_ts": time.time() + _COOKIE_MAX_AGE}
            _save_cache(self.cache)
            if "i=1" not in url:
                url = url + ("&" if "?" in url else "?") + "i=1"
        raise RuntimeError("连续 3 次请求仍被 InfinityFree 挑战拦截，请稍后再试")


# ---------- API 客户端 ----------
class ApiClient:
    def __init__(self, base: str = DEFAULT_BASE, use_file_cache: bool = True):
        self.session = ApiSession(base, use_file_cache)
        self.cache = self.session.cache

    @staticmethod
    def calc_token(seed: str, username: str, password: str) -> str:
        return hashlib.sha256(f"{username}:{password}:{seed}".encode()).hexdigest()

    def _cached_token(self, identity: str, username: str, password: str):
        """取缓存 token；无缓存/跨小时/超时则 get_seed 重算。返回 token。"""
        key = f"{username}:{identity}"
        now = time.time()
        t = self.cache.get("tokens", {}).get(key)
        if t and t.get("slot") == datetime.now().strftime("%Y%m%d%H") \
                and now - t.get("ts", 0) < _TOKEN_MAX_AGE:
            return t["token"]
        body = self.session.request(self.session.base + "?" + urllib.parse.urlencode(
            {"action": "get_seed", "identity": identity}))
        data = json.loads(body)
        if not data.get("success"):
            raise RuntimeError(f"get_seed 失败: {data}")
        seed = data["data"]["seed"]
        token = self.calc_token(seed, username, password)
        self.cache.setdefault("tokens", {})[key] = {
            "slot": data["data"].get("slot") or datetime.now().strftime("%Y%m%d%H"),
            "token": token,
            "ts": now,
        }
        _save_cache(self.cache)
        return token

    def call(self, action: str, username: str, password: str, identity: str,
             extra: dict | None = None, method: str = "GET") -> dict:
        """调用端点：带缓存 token 请求；401（跨小时轮换）时自动重取 token 重试一次。

        普通调用只有 1 次 HTTP 往返，速度与直接调 API 基本一致。
        """
        base_params = {"username": username, "action": action}
        if extra:
            base_params.update(extra)

        token = self._cached_token(identity, username, password)
        data = self._parse_json(self._raw_call(base_params, token, method))

        # 401 → token 跨小时失效，强制刷新重试一次
        if not data.get("success") and data.get("code") == 401:
            key = f"{username}:{identity}"
            self.cache.get("tokens", {}).pop(key, None)
            token = self._cached_token(identity, username, password)
            data = self._parse_json(self._raw_call(base_params, token, method))
        return data

    @staticmethod
    def _parse_json(body: str) -> dict:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            snippet = body[:200].replace("\n", " ")
            raise RuntimeError(f"服务端返回了非 JSON 响应（可能是临时故障或挑战异常）：{snippet}")

    def _raw_call(self, base_params: dict, token: str, method: str) -> str:
        params = dict(base_params)
        params["token"] = token
        url = self.session.base + "?" + urllib.parse.urlencode(params)
        if method == "POST":
            return self.session.request(self.session.base, urllib.parse.urlencode(params).encode())
        return self.session.request(url)


# ---------- CLI ----------
def main(argv=None):
    ap = argparse.ArgumentParser(description="morning-reading API 自动客户端（自动过 InfinityFree 挑战）")
    ap.add_argument("action", help="端点 action：get_seed/verify_token/status/students/stats/add_record/cancel_record/penalize 等")
    ap.add_argument("--identity", default="teacher", choices=["record", "teacher", "superadmin"], help="身份，默认 teacher")
    ap.add_argument("--user", "--username", required=True, help="用户名（年级-班号 或 superadmin）")
    ap.add_argument("--pass", "--password", dest="password", required=True, help="对应身份的密码")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"API 地址，默认 {DEFAULT_BASE}")
    ap.add_argument("--period", default=None, help="stats 的统计周期：day/week/month/semester/total")
    ap.add_argument("--student-no", default=None, help="add_record/cancel_record/penalize 的学号")
    ap.add_argument("--grade-class", default=None, help="superadmin 跨班时指定班级，如 9-6")
    ap.add_argument("--no-cache", action="store_true", help="不使用本地缓存文件（cookie/token 均不落盘）")
    ap.add_argument("--raw", action="store_true", help="输出原始 JSON（不做中文美化）")
    args = ap.parse_args(argv)

    client = ApiClient(args.base, use_file_cache=not args.no_cache)

    if args.action == "get_seed":
        body = client.session.request(client.session.base + "?" + urllib.parse.urlencode(
            {"action": "get_seed", "identity": args.identity}))
        print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
        return

    extra = {}
    if args.period:
        extra["period"] = args.period
    if args.student_no:
        extra["student_no"] = args.student_no
    if args.grade_class:
        extra["grade_class"] = args.grade_class

    method = "POST" if args.action in ("add_record", "cancel_record", "penalize") else "GET"
    data = client.call(args.action, args.user, args.password, args.identity, extra, method)
    if args.raw:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 网络/JSON 错误也给出可读信息
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
