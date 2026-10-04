"""
远测（telemetry）：匿名上报运行情况，用于排查"老师那边到底出了什么问题"。

原则：
1. **失败绝不影响功能**：全部在后台线程里做，异常一律吞掉。
2. **省 Supabase 免费额度**：每天有行数上限，超了只保留错误事件和汇总事件；
   成功的检查类事件会做去重（同一小时内同类型只报一次）。
3. **数据里不放任何隐私内容**：只有版本号、系统版本、错误类型/位置、
   匿名机器标识（机器 GUID 的 sha256 前 16 位，不可逆），没有用户名/路径/密码。
4. 本地同时写一份 `telemetry.log`，网络不通时也能在教室电脑上排查。

上报表结构（不变，避免和已有 Supabase 表冲突）：
    version / event_type / os_version / details(jsonb)
详细上下文都塞在 details 里。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import threading
import time
import urllib.request
import uuid

SUPABASE_URL = "https://tiofmybnepcheudgfysa.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRpb2ZteWJuZXBjaGV1ZGdmeXNhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA5NjYyMjYsImV4cCI6MjEwNjU0MjIyNn0."
    "6CTEoVO9QrmBmxkUxNqgWhx6vQ1I-ikI9yy8rImVAA8"
)

DATA_DIR = os.environ.get("IDIOT_LAUNCH_DATA", r"D:\IdiotLaunch\data")
STATE_PATH = os.path.join(DATA_DIR, "telemetry_state.json")
LOCAL_LOG = os.path.join(DATA_DIR, "telemetry.log")

# 每天最多上报多少行（免费版额度有限；错误事件不受此限制，但也有硬上限）
DAILY_ROW_LIMIT = 300
DAILY_ERROR_LIMIT = 120
# 非错误事件同类去重窗口（秒）
DEDUPE_WINDOW = 1800

_pending: list = []
_send_lock = threading.Lock()
_flight = threading.Semaphore(4)
_session_id = uuid.uuid4().hex[:8]
_client_id_cache: str | None = None


# ── 上下文 ────────────────────────────────────────────
def _client_id() -> str:
    """匿名机器标识：注册表 MachineGuid 的 sha256 前 16 位（不可逆）。"""
    global _client_id_cache
    if _client_id_cache:
        return _client_id_cache
    raw = ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography") as k:
            raw = str(winreg.QueryValueEx(k, "MachineGuid")[0])
    except Exception:
        raw = platform.node()
    _client_id_cache = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return _client_id_cache


def _version() -> str:
    try:
        from src.core import LAUNCHER_VERSION

        return LAUNCHER_VERSION
    except Exception:
        return "unknown"


def _os_version() -> str:
    try:
        return f"{platform.system()} {platform.release()} {platform.version()}"
    except Exception:
        return "unknown"


def _enabled() -> bool:
    try:
        from src.core import is_telemetry_enabled

        return is_telemetry_enabled()
    except Exception:
        return True


# ── 本地状态（配额/去重） ─────────────────────────────
def _load_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_state(state: dict) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass


def _quota_ok(is_error: bool, event_type: str) -> bool:
    state = _load_state()
    today = time.strftime("%Y-%m-%d")
    if state.get("day") != today:
        state = {"day": today, "rows": 0, "errors": 0, "seen": {}}
    seen = state.setdefault("seen", {})
    last = float(seen.get(event_type, 0))
    now = time.time()
    if not is_error and now - last < DEDUPE_WINDOW:
        return False
    if is_error:
        if state.get("errors", 0) >= DAILY_ERROR_LIMIT:
            return False
        state["errors"] = state.get("errors", 0) + 1
    else:
        if state.get("rows", 0) >= DAILY_ROW_LIMIT:
            return False
    state["rows"] = state.get("rows", 0) + 1
    seen[event_type] = now
    _save_state(state)
    return True


def _local_log(payload: dict) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.isfile(LOCAL_LOG) and os.path.getsize(LOCAL_LOG) > 256 * 1024:
            try:
                os.replace(LOCAL_LOG, LOCAL_LOG + ".1")
            except OSError:
                pass
        line = (f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {payload.get('event_type')} "
                f"{json.dumps(payload.get('details', {}), ensure_ascii=False)}\n")
        with open(LOCAL_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ── 上报 ──────────────────────────────────────────────
def _post(payload: dict) -> bool:
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/telemetry",
            data=data,
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _flush_queue() -> None:
    global _pending
    with _send_lock:
        if not _pending:
            return
        keep = []
        for i, event in enumerate(_pending):
            if not _post(event):
                keep = _pending[i:]
                break
        _pending = keep[-50:]


def report_event(event_type: str, details: dict | None = None) -> None:
    """异步上报一个事件。不允许抛异常。"""
    try:
        if not _enabled():
            return
        is_error = event_type in ("error", "crash") or str(event_type).endswith("_error")
        if not _quota_ok(is_error, event_type):
            return

        payload = {
            "version": _version(),
            "event_type": event_type,
            "os_version": _os_version(),
            "details": {
                "cid": _client_id(),
                "sid": _session_id,
                "pid": os.getpid(),
                "ts": int(time.time()),
                **(details or {}),
            },
        }
        _local_log(payload)

        def _worker():
            global _pending
            if not _flight.acquire(timeout=5):
                return
            try:
                _flush_queue()
                if not _post(payload):
                    with _send_lock:
                        _pending.append(payload)
                        del _pending[:-50]
            finally:
                _flight.release()

        threading.Thread(target=_worker, daemon=True).start()
    except Exception:
        pass


def report_error(where: str, error: BaseException | str, extra: dict | None = None) -> None:
    """统一格式的错误上报（排查问题时最有用的一类事件）。"""
    detail = {"where": where, "error_type": type(error).__name__}
    if isinstance(error, BaseException):
        detail["error"] = str(error)[:300]
    else:
        detail["error"] = str(error)[:300]
    if extra:
        detail.update(extra)
    report_event("error", detail)


def flush(timeout: float = 2.0) -> None:
    """尽力把队列里的剩余事件发出去（退出前调用）。"""
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with _send_lock:
                empty = not _pending
            if empty:
                return
            _flush_queue()
            time.sleep(0.1)
    except Exception:
        pass
