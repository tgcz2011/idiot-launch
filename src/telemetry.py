"""
Supabase 遥测上报模块
异步上报，失败不影响主流程
"""
import json
import platform
import threading
import urllib.request

SUPABASE_URL = "https://tiofmybnepcheudgfysa.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRpb2ZteWJuZXBjaGV1ZGdmeXNhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA5NjYyMjYsImV4cCI6MjEwNjU0MjIyNn0.6CTEoVO9QrmBmxkUxNqgWhx6vQ1I-ikI9yy8rImVAA8"

# 本地缓存目录，网络失败时暂存
CACHE_DIR = None
_pending_events = []
_send_lock = threading.Lock()


def _get_os_version():
    try:
        return f"{platform.system()} {platform.release()} {platform.version()}"
    except Exception:
        return "unknown"


def _get_version():
    try:
        from src.core import LAUNCHER_VERSION
        return LAUNCHER_VERSION
    except Exception:
        return "unknown"


def _send_to_supabase(payload):
    """发送到 Supabase，失败时缓存到本地"""
    global _pending_events
    try:
        data = json.dumps(payload).encode("utf-8")
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
            return resp.status == 201
    except Exception:
        return False


def _flush_cache():
    """尝试发送缓存的事件"""
    global _pending_events
    with _send_lock:
        if not _pending_events:
            return
        remaining = []
        for event in _pending_events:
            if not _send_to_supabase(event):
                remaining.append(event)
                break  # 网络还是不行，剩下的下次再试
        _pending_events = remaining


def report_event(event_type, details=None):
    """
    上报遥测事件（异步非阻塞）
    
    Args:
        event_type: 事件类型，如 launch / crash / update_check / download_success / feature_use
        details: 附加信息字典
    """
    payload = {
        "version": _get_version(),
        "event_type": event_type,
        "os_version": _get_os_version(),
        "details": details or {},
    }

    def _worker():
        global _pending_events
        # 先尝试发送缓存
        _flush_cache()
        # 发送当前事件
        if not _send_to_supabase(payload):
            with _send_lock:
                _pending_events.append(payload)
                # 最多缓存 50 条
                if len(_pending_events) > 50:
                    _pending_events = _pending_events[-50:]

    threading.Thread(target=_worker, daemon=True).start()
