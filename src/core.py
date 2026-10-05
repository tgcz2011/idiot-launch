"""
core.py — 核心逻辑：倒计时启动/退出、早读账号、自动更新、守护进程、状态与日志。

架构（V3）：
  Flutter 前端  ──HTTP /api──▶  backend_server.py（后端进程）
                                     ├─ daemon 线程（更新检查 / 空闲静默更新 / 快捷方式守护 / 清理）
                                     ├─ tkinter 悬浮球线程
                                     └─ pystray 托盘线程
  子进程：--countdown-app（壁纸/屏保）、--morning-browser（早晚读浏览器）

约定：
  * 所有可写数据都在 D:\\IdiotLaunch\\data，冰点还原不影响。
  * state.json / settings.json 的读改写全部走 _state_lock，避免多线程互相覆盖。
"""
import ctypes
import hashlib
import json
import logging
import logging.handlers
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

# ── 常量 ──────────────────────────────────────────────
APP_NAME = "傻瓜启动器"
# 早读站点地址统一放在 morning_config，避免多处硬编码
try:
    from src.morning_config import MORNING_API_URL, MORNING_READING_URL
except ImportError:  # 以 `python src/core.py` / 老脚本方式直接导入时
    from morning_config import MORNING_API_URL, MORNING_READING_URL  # type: ignore

UPDATE_DIR = r"D:\IdiotLaunch\data"
STATE_FILE = os.path.join(UPDATE_DIR, "state.json")
SETTINGS_FILE = os.path.join(UPDATE_DIR, "settings.json")
DAEMON_LOG = os.path.join(UPDATE_DIR, "daemon.log")
COMMAND_FILE = os.path.join(UPDATE_DIR, "command.json")
LOG_DIR = UPDATE_DIR

# 更新检查间隔（秒）。历史值是 10 分钟，教室共用出口 IP 时太频繁。
CHECK_INTERVAL = 60 * 60
# 空闲多久才允许静默自我更新（秒）。3 分钟太激进：老师站着讲课 3 分钟就会被强杀重装。
IDLE_THRESHOLD = 600
# 启动后如果距离上次检查超过这个时间，就立刻检查一次
STARTUP_CHECK_GRACE = 10 * 60

DOWNLOAD_TIMEOUT = 900
DOWNLOAD_RETRY = 3
MAX_DOWNLOAD_FAILURES = 3
# 下载进度多久没更新就认为这次下载已经死了。
# 用户实测反馈：下载被"退出程序/安装更新/断网"打断后，状态一直停在 downloading，
# 界面就永远显示"正在后台下载 0%"，看上去像卡住了。
DOWNLOAD_STALE_SECONDS = 300

DAEMON_MUTEX = "IdiotLaunch_Daemon_Single"
DAEMON_QUIT_EVENT = "IdiotLaunch_Quit"

# 下载镜像源（aria2 会同时从多个源分块下载，空字符串 = GitHub 直连）
DOWNLOAD_MIRRORS = [
    "",                                    # GitHub 直连（最可靠）
    "https://ghproxy.com/",                # ghproxy 老牌
    "https://mirror.ghproxy.com/",         # ghproxy 镜像
    "https://gh-proxy.com/",               # GH-Proxy
    "https://ghfast.top/",                 # ghfast
    "https://ghproxy.net/",                # ghproxy.net
    "https://gh.llkk.cc/",                 # LLKK 公益加速
    "https://hub.gitmirror.com/",          # GitMirror
    "https://ghproxy.homeboyc.cn/",        # 大文件稳定
    "https://ghps.cc/",                    # ghps
    "https://gh.api.99988866.xyz/",        # 99988866
]

LAUNCHER_VERSION = "3.0.0.0"
LAUNCHER_GITHUB_API = "https://api.github.com/repos/tgcz2011/idiot-launch/releases/latest"
LAUNCHER_TAGS_API = "https://api.github.com/repos/tgcz2011/idiot-launch/tags?per_page=30"
LAUNCHER_SETUP_PREFIX = "IdiotLaunch_Setup_"
LAUNCHER_MIN_SIZE = 5 * 1024 * 1024
LAUNCHER_INSTALL_DIR = r"D:\IdiotLaunch"
LAUNCHER_INSTALL_EXE = os.path.join(LAUNCHER_INSTALL_DIR, "IdiotLaunch.exe")

# 更新相关常量
SUPABASE_URL = "https://tiofmybnepcheudgfysa.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRpb2ZteWJuZXBjaGV1ZGdmeXNhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA5NjYyMjYsImV4cCI6MjEwNjU0MjIyNn0."
    "6CTEoVO9QrmBmxkUxNqgWhx6vQ1I-ikI9yy8rImVAA8"
)

# 构建时注入的 GitHub Token（不入 git）；没有就用未认证 API
try:
    from src._secrets import GITHUB_TOKEN  # type: ignore
except ImportError:
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# 默认设置
DEFAULT_SETTINGS = {
    "theme": "system",        # system / light / dark
    "auto_update": True,      # 是否允许后台自动下载/静默安装更新
    "telemetry": True,        # 是否上报匿名运行统计
    "show_tray_hint": True,   # 关闭窗口时是否提示"已最小化到托盘"
}


# ── Win32 基础 ────────────────────────────────────────
# use_last_error=True + ctypes.get_last_error()：直接用 windll 读 GetLastError()
# 在 ctypes 中间调用后可能拿到过期值，会让"单实例互斥量"判定失败，
# 结果就是两个 daemon 同时跑 → 同一个更新包被下载两遍（线上日志里出现过）。
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _mutex_acquire(name: str):
    """创建命名互斥量；已存在则返回 None。"""
    try:
        _kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = _kernel32.CreateMutexW(None, False, name)
        if not handle:
            return None
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            _kernel32.CloseHandle(handle)
            return None
        return handle
    except Exception:
        return None


def _event_open(name: str, access: int = 0x0002):
    try:
        _kernel32.OpenEventW.restype = ctypes.c_void_p
        return _kernel32.OpenEventW(access, False, name)
    except Exception:
        return None


def _event_create(name: str):
    try:
        _kernel32.CreateEventW.restype = ctypes.c_void_p
        return _kernel32.CreateEventW(None, False, False, name)
    except Exception:
        return None


def _wait_event(handle, ms: int) -> bool:
    if not handle:
        time.sleep(ms / 1000.0)
        return False
    try:
        return _kernel32.WaitForSingleObject(handle, ms) == 0
    except Exception:
        time.sleep(ms / 1000.0)
        return False


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds() -> float:
    """系统空闲秒数（距上次键鼠输入）。取不到时返回 0（= 正在使用，宁可不更新）。"""
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0
        tick = ctypes.windll.kernel32.GetTickCount()
        return max(0.0, (tick - lii.dwTime) / 1000.0)
    except Exception:
        return 0.0


def boot_id() -> int:
    """本次开机的标识（时间戳形式）。用于"每次开机只提示一次"这类逻辑。"""
    try:
        _kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        uptime_ms = int(_kernel32.GetTickCount64())
    except Exception:
        try:
            uptime_ms = int(ctypes.windll.kernel32.GetTickCount())
        except Exception:
            uptime_ms = 0
    return int(time.time() - uptime_ms / 1000.0)


# ── 日志 ──────────────────────────────────────────────
def _ensure_update_dir() -> None:
    os.makedirs(UPDATE_DIR, exist_ok=True)


_log_lock = threading.Lock()
_logging_ready = False


def setup_logging(name: str, level: int = logging.INFO) -> None:
    """把 logging 输出落到 D 盘的独立文件（每个入口一个文件，避免抢写）。

    历史问题：console=False 的打包程序里 stderr 是 None，所有 log.warning
    全部丢失，出问题只能靠猜。
    """
    global _logging_ready
    if _logging_ready:
        return
    _logging_ready = True
    try:
        _ensure_update_dir()
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(LOG_DIR, f"{name}.log"),
            maxBytes=512 * 1024, backupCount=2, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger()
        root.setLevel(level)
        root.addHandler(handler)
    except Exception:
        pass


def log_daemon(msg: str) -> None:
    try:
        with _log_lock:
            _ensure_update_dir()
            line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
            # 轮转：main → .1 → .2 → .3（最多 3 份备份）
            if os.path.isfile(DAEMON_LOG) and os.path.getsize(DAEMON_LOG) > 256 * 1024:
                for i in (2, 1):
                    src = f"{DAEMON_LOG}.{i}"
                    dst = f"{DAEMON_LOG}.{i + 1}"
                    if os.path.isfile(src):
                        try:
                            if os.path.isfile(dst):
                                os.remove(dst)
                            os.replace(src, dst)
                        except OSError:
                            pass
                try:
                    os.replace(DAEMON_LOG, DAEMON_LOG + ".1")
                except OSError:
                    pass
            with open(DAEMON_LOG, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


# ── 设置 ──────────────────────────────────────────────
def load_settings() -> dict:
    cfg = dict(DEFAULT_SETTINGS)
    try:
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k in DEFAULT_SETTINGS:
                    if k in data:
                        cfg[k] = data[k]
    except Exception:
        pass
    return cfg


def save_settings(patch: dict) -> dict:
    cfg = load_settings()
    for k, v in (patch or {}).items():
        if k in DEFAULT_SETTINGS:
            cfg[k] = v
    try:
        _ensure_update_dir()
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
    except Exception as e:
        log_daemon(f"设置保存失败: {e}")
    return cfg


def is_telemetry_enabled() -> bool:
    try:
        return bool(load_settings().get("telemetry", True))
    except Exception:
        return True


def is_auto_update_enabled() -> bool:
    try:
        return bool(load_settings().get("auto_update", True))
    except Exception:
        return True


def idle_threshold_seconds() -> int:
    """空闲判定阈值。设置里可以调，默认 10 分钟。"""
    try:
        v = int(load_settings().get("idle_minutes", IDLE_THRESHOLD // 60))
        return max(60, v * 60)
    except Exception:
        return IDLE_THRESHOLD


# ── 版本 ──────────────────────────────────────────────
def parse_version(v: str) -> tuple:
    """返回 ((主版本 4 段元组), 预发布类型权重, 预发布数字)。

    正式版=100 > rc=3 > beta=2 > alpha=1 > 未知=0。
    """
    import re

    v = (v or "").strip().lstrip("vV")
    pre_type = 100
    pre_num = 0
    if "-" in v:
        main_part, pre_part = v.split("-", 1)
        pre_lower = pre_part.lower()
        if "alpha" in pre_lower:
            pre_type = 1
        elif "beta" in pre_lower:
            pre_type = 2
        elif "rc" in pre_lower:
            pre_type = 3
        else:
            pre_type = 0
        if pre_type < 100:
            m = re.search(r"\d+", pre_part)
            pre_num = int(m.group()) if m else 0
    else:
        main_part = v

    parts = []
    for p in main_part.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 4:
        parts.append(0)
    return (tuple(parts[:4]), pre_type, pre_num)


def compare_versions(v1: str, v2: str) -> int:
    a, b = parse_version(v1), parse_version(v2)
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def is_beta_version(version: str) -> bool:
    v = (version or "").lower()
    return any(tag in v for tag in ("beta", "alpha", "rc", "pre", "-dev"))


# ── Countdown Desktop（已合并进本项目） ────────────────
def _countdown_env() -> dict:
    env = os.environ.copy()
    env["COUNTDOWN_CONFIG_DIR"] = os.path.join(LAUNCHER_INSTALL_DIR, "data", "countdown")
    return env


def _spawn_countdown(extra_args: list) -> bool:
    try:
        subprocess.Popen(
            [sys.executable, "--countdown-app", *extra_args, "--auto-check-update", "off"],
            creationflags=0x00000008,  # DETACHED_PROCESS
            close_fds=True,
            env=_countdown_env(),
        )
        return True
    except Exception as e:
        log_daemon(f"启动倒计时失败 {extra_args}: {e}")
        return False


def launch_countdown(exam_type: str) -> bool:
    return _spawn_countdown(["--exam", exam_type])


def launch_custom() -> bool:
    return _spawn_countdown([])


def launch_settings() -> bool:
    return _spawn_countdown(["--settings"])


def is_running() -> bool:
    try:
        handle = _kernel32.OpenMutexW(0x00100000, False, "CountdownDesktop_Single")
        if handle:
            _kernel32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


def quit_countdown(timeout: float = 8.0) -> bool:
    """通知 Countdown Desktop 优雅退出（命名事件），并按需等待。"""
    if not is_running():
        return True
    event = _event_open("CountdownDesktop_Quit")
    if not event:
        return False
    try:
        _kernel32.SetEvent(event)
    finally:
        _kernel32.CloseHandle(event)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.25)
        if not is_running():
            return True
    return False


# ── 早读 ──────────────────────────────────────────────
def _morning_client():
    from src.morning_api_client import ApiClient

    return ApiClient()


def load_morning_config() -> dict:
    from src import morning_config

    return morning_config.load()


def save_morning_config(config: dict, persistent: bool = True) -> bool:
    from src import morning_config

    return morning_config.save(config, persistent=persistent)


def is_morning_logged_in() -> bool:
    cfg = load_morning_config()
    return bool(cfg.get("grade") and cfg.get("class_number") and cfg.get("password"))


def verify_morning_login(grade, class_number, password):
    """校验账号密码。返回 (ok, periods, error_msg)。

    错误信息尽量区分"账号密码错"和"网络/服务端异常"，否则老师会一直重试密码。
    """
    try:
        client = _morning_client()
        username = f"{grade}-{class_number}"
        ok, data, err = client.call("status", username, password, "record")
        if not ok:
            return False, None, err or "无法连接早读服务器，请检查网络后重试"
        if not data.get("success"):
            code = data.get("code")
            msg = str(data.get("message") or data.get("msg") or "").strip()
            if code == 401 or "密码" in msg or "账号" in msg:
                return False, None, "账号或密码错误，请检查后重试"
            return False, None, msg or "服务器返回异常，请稍后重试"
        periods = _parse_periods(str(data.get("data", {}).get("period_text", "")))
        return True, (periods or None), ""
    except Exception as e:
        log_daemon(f"早读登录校验异常: {type(e).__name__}: {e}")
        return False, None, "网络连接失败，请检查网络后重试"


def _parse_periods(period_text: str) -> dict:
    """解析 "早读：06:20-07:10，晚读：17:40-21:30"。

    解析不出来只记日志、返回空，绝不能因此把登录判成失败。
    """
    periods = {}
    try:
        for key, label in (("morning", "早读"), ("evening", "晚读")):
            if label not in period_text:
                continue
            # 兼容全角/半角冒号和分隔符
            seg = period_text.split(label, 1)[1]
            seg = seg.lstrip("：: ")
            seg = seg.split("，")[0].split(",")[0].split("；")[0].split(";")[0]
            if "-" not in seg:
                continue
            start, end = seg.split("-", 1)
            periods[key] = {"start": start.strip(), "end": end.strip()}
    except Exception as e:
        log_daemon(f"早读时间段解析失败({period_text!r}): {e}")
    return periods


def refresh_morning_periods() -> None:
    """后台定期刷新时间段（悬浮球按时段显示）。保持原有的持久性设置。"""
    try:
        cfg = load_morning_config()
        grade = str(cfg.get("grade", "")).strip()
        class_number = str(cfg.get("class_number", "")).strip()
        password = str(cfg.get("password", "")).strip()
        if not (grade and class_number and password):
            return
        ok, periods, _ = verify_morning_login(grade, class_number, password)
        if ok and periods:
            cfg["periods"] = periods
            # 关键：沿用原来的 persistent，不能把"仅本次登录"变成"永久保存"
            save_morning_config(cfg, persistent=bool(cfg.get("persistent", True)))
            log_daemon(f"早读时间段已刷新: {periods}")
    except Exception as e:
        log_daemon(f"刷新早读时间段异常: {type(e).__name__}: {e}")


def get_morning_students(config: dict = None) -> list:
    """返回 [{"student_no": 1, "name": "张三"}, ...]；失败返回空列表（调用方需自辨）。"""
    if config is None:
        config = load_morning_config()
    if not (config.get("grade") and config.get("class_number") and config.get("password")):
        return []
    try:
        client = _morning_client()
        username = f"{config.get('grade')}-{config.get('class_number')}"
        ok, data, err = client.call("students", username, config.get("password", ""), "record")
        if not ok:
            log_daemon(f"获取学生列表失败: {err}")
            return []
        if not data.get("success"):
            return []
        students = data.get("data", {}).get("students", []) or []
        out = []
        for s in students:
            if not isinstance(s, dict):
                continue
            no = s.get("student_no", s.get("no"))
            name = s.get("name", s.get("student_name"))
            if name is None:
                continue
            out.append({"student_no": no, "name": str(name)})
        return out
    except Exception as e:
        log_daemon(f"早读学生列表异常: {type(e).__name__}: {e}")
        return []


def open_morning_reading() -> bool:
    """打开早晚读内嵌浏览器（独立进程，不带任何凭据参数）。"""
    from src.floating_button import open_morning_browser

    return open_morning_browser()


# ── 状态文件 ──────────────────────────────────────────
_state_lock = threading.RLock()


def load_state() -> dict:
    try:
        _ensure_update_dir()
        if os.path.isfile(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_state(state: dict) -> None:
    """原子写入 + 加锁（多个线程都会读改写，不加锁会互相覆盖）。"""
    try:
        with _state_lock:
            _ensure_update_dir()
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, STATE_FILE)
    except Exception as e:
        log_daemon(f"状态保存失败: {e}")


def update_state(patch: dict) -> dict:
    """加锁的"读-改-写"，供多个线程安全地改状态。"""
    with _state_lock:
        state = load_state()
        state.update(patch or {})
        save_state(state)
        return state


def set_daemon_status(activity: str, progress: float = 0, detail: str = "",
                      download_tag: str = "") -> None:
    with _state_lock:
        state = load_state()
        daemon = {
            "activity": activity,
            "progress": float(progress),
            "detail": detail,
            "timestamp": time.time(),
            "pid": os.getpid(),
        }
        if download_tag:
            daemon["download_tag"] = download_tag
        state["daemon"] = daemon
        save_state(state)


def get_daemon_status() -> dict | None:
    daemon = load_state().get("daemon")
    if not daemon:
        return None
    if time.time() - daemon.get("timestamp", 0) > 300:
        return None
    return daemon


def is_daemon_running() -> bool:
    """只查询，不创建互斥量（创建会让正在启动的 daemon 误判）。"""
    try:
        _kernel32.OpenMutexW.restype = ctypes.c_void_p
        handle = _kernel32.OpenMutexW(0x00100000, False, DAEMON_MUTEX)
        if handle:
            _kernel32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


# ── 命令通道 ──────────────────────────────────────────
def send_command(cmd: str, **params) -> None:
    try:
        with _state_lock:
            _ensure_update_dir()
            data = {"cmd": cmd, "timestamp": time.time()}
            data.update(params)
            tmp = COMMAND_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, COMMAND_FILE)
    except Exception:
        pass


def poll_command() -> dict | None:
    try:
        with _state_lock:
            if not os.path.isfile(COMMAND_FILE):
                return None
            with open(COMMAND_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            os.remove(COMMAND_FILE)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ── 下载 ──────────────────────────────────────────────
def sha256_of(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def verify_sha256(file_path: str, expected: str) -> bool:
    """expected 为空时跳过（旧 release 没有 digest 字段）。"""
    expected = (expected or "").strip().lower().removeprefix("sha256:")
    if not expected:
        return True
    try:
        return sha256_of(file_path) == expected
    except OSError:
        return False


def _installer_files(dest_path: str):
    """安装包相关的所有文件（含 aria2 分片/控制文件）。"""
    base = os.path.basename(dest_path)
    try:
        for name in os.listdir(UPDATE_DIR):
            if name == base or name.startswith(base + "."):
                yield os.path.join(UPDATE_DIR, name)
    except OSError:
        return


def _remove_installer(dest_path: str) -> None:
    if not dest_path:
        return
    for p in list(_installer_files(dest_path)):
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


# ── 下载状态（界面靠它显示进度） ───────────────────────

def set_download_state(version: str, percent: float, status: str,
                       installer: str = "", release_notes: str = "") -> None:
    """把下载进度写进 state.json。

    历史 bug：下载过程中只更新了 daemon.progress，launcher_download.progress
    永远停在 0 —— 界面于是永远显示"正在后台下载 0%"，看起来像卡死了。
    """
    with _state_lock:
        st = load_state()
        st["launcher_download"] = {
            "version": str(version),
            "progress": round(max(0.0, min(100.0, float(percent))), 1),
            "status": status,
            "installer": installer,
            "release_notes": release_notes,
            "updated_at": time.time(),
        }
        save_state(st)


def clear_download_state(reason: str = "") -> None:
    with _state_lock:
        st = load_state()
        if st.pop("launcher_download", None) is None:
            return
        save_state(st)
    if reason:
        log_daemon(f"清除下载状态：{reason}")


def get_download_state() -> dict:
    """界面用的下载状态（带"是不是已经死了"的判断）。

    超过 DOWNLOAD_STALE_SECONDS 没有进度更新，就认为这次下载已经结束。
    程序被关掉、装更新、断网都会留下半截 downloading 状态，
    不清掉的话界面会永远显示"正在后台下载"。
    """
    dl = dict(load_state().get("launcher_download") or {})
    if not dl:
        return {}
    if dl.get("status") == "downloading":
        updated = float(dl.get("updated_at", 0) or 0)
        if not updated or time.time() - updated > DOWNLOAD_STALE_SECONDS:
            dl["status"] = "interrupted"
    return dl


def _current_download_installer() -> str:
    """正在下载的安装包路径（清理残留时不能删它）。"""
    dl = get_download_state()
    if dl.get("status") == "downloading":
        return str(dl.get("installer", "") or "")
    return ""


def touch_download_state() -> None:
    """下载线程还活着：把 updated_at 往后推。

    慢网络下可能好几分钟都停在同一个百分比（还在换镜像、建连接、拉分片），
    不能因为"进度一直没变"就被界面判成"已中断"。
    daemon 主循环里调用，最多每分钟写一次盘。
    """
    with _state_lock:
        st = load_state()
        dl = st.get("launcher_download") or {}
        if dl.get("status") != "downloading":
            return
        now = time.time()
        if now - float(dl.get("updated_at", 0) or 0) < 60:
            return
        dl["updated_at"] = now
        st["launcher_download"] = dl
        save_state(st)


def _clear_stale_download_on_start() -> None:
    """daemon 启动时收拾上一次没下完的下载状态。

    实测（beta27→beta28）：上一次下载被中断后 launcher_download 一直停在
    downloading/0%，界面永远显示"正在后台下载 0%"，用户以为一直在下载。
    """
    dl = load_state().get("launcher_download") or {}
    if not dl:
        return
    version = str(dl.get("version", ""))
    status = str(dl.get("status", ""))
    updated = float(dl.get("updated_at", 0) or 0)
    reason = ""
    if not version:
        reason = "没有版本号"
    elif compare_versions(version, LAUNCHER_VERSION) <= 0:
        reason = f"v{version} 已经不高于当前版本"
    elif status == "failed":
        reason = f"v{version} 上次下载失败"
    elif status == "downloading" and (
            not updated or time.time() - updated > DOWNLOAD_STALE_SECONDS):
        reason = f"v{version} 上次下载被中断"
    if reason:
        clear_download_state(reason)


def cleanup_stale_downloads(keep_path: str = "") -> int:
    """清理 data 目录里的下载残留：断点分片、过期安装包、旧 CD 安装包。

    历史问题：每失败一次下载就在 D 盘留下几十 MB 的 .part 文件，
    加上每个版本一个安装包，实测能堆到 300MB+ 且永不回收。
    """
    removed = 0
    now = time.time()
    keep = os.path.basename(keep_path) if keep_path else ""
    try:
        for name in os.listdir(UPDATE_DIR):
            path = os.path.join(UPDATE_DIR, name)
            if not os.path.isfile(path):
                continue
            stale_part = (name.endswith(".part") or name.endswith(".aria2")
                          or ".part" in name)
            legacy_cd = name.startswith("CountdownDesktop_Setup_")
            old_launcher = (name.startswith(LAUNCHER_SETUP_PREFIX)
                            and name.endswith(".exe") and name != keep)
            if not (stale_part or legacy_cd or old_launcher):
                continue
            if keep and name.startswith(keep + "."):
                # 当前正在续传的分片，保留
                continue
            try:
                # 分片文件可能正在被 aria2 使用：只清理 1 小时以上没动过的
                if stale_part and now - os.path.getmtime(path) < 3600:
                    continue
                os.remove(path)
                removed += 1
            except OSError:
                pass
    except OSError:
        pass
    if removed:
        log_daemon(f"清理下载残留 {removed} 个文件")
    return removed


def _adopt_downloaded_file(dest_path: str, url: str) -> None:
    """aria2 会优先采用服务器 Content-Disposition 里的文件名，可能不是 --out。

    实测：`--out probe.exe` + GitHub 资源 → 文件被存成
    `IdiotLaunch_Setup_x.y.z.exe`，于是调用方"下载成功但目标文件不存在"。
    生产环境两边名字本来就一样，这里只是兜底。
    """
    if not dest_path or os.path.isfile(dest_path):
        return
    dirname = os.path.dirname(dest_path)
    wanted = os.path.basename(dest_path)
    try:
        name = os.path.basename(urllib.parse.urlparse(url).path)
    except Exception:
        name = ""
    if not name or name == wanted:
        return
    src = os.path.join(dirname, name)
    if not os.path.isfile(src):
        return
    try:
        os.replace(src, dest_path)
        log_daemon(f"下载落盘文件名与目标不一致，已改名: {name} -> {wanted}")
    except OSError as e:
        log_daemon(f"改名下载文件失败: {type(e).__name__}: {e}")


def download_installer(url: str, dest_path: str, tag: str = "",
                       on_progress=None) -> bool:
    """aria2 多源分块下载（16 连接/源），失败重试 3 轮。

    [on_progress] 让调用方把百分比写进自己的状态（界面要显示进度条）。
    """
    from src.aria2_downloader import download_with_aria2
    from src.telemetry import report_event

    _ensure_update_dir()
    urls = [(m + url) if m else url for m in DOWNLOAD_MIRRORS]
    start_time = time.time()

    def _progress(percent, speed):
        set_daemon_status(
            "downloading", float(percent),
            f"下载中 {percent}% ({speed // 1024} KB/s)", download_tag=tag)
        if on_progress is not None:
            try:
                on_progress(percent)
            except Exception:
                pass

    for attempt in range(DOWNLOAD_RETRY):
        log_daemon(f"aria2 下载尝试 ({attempt + 1}/{DOWNLOAD_RETRY})，{len(urls)} 个源")
        ok = download_with_aria2(urls, dest_path,
                                 progress_callback=_progress, timeout=DOWNLOAD_TIMEOUT)
        if ok:
            _adopt_downloaded_file(dest_path, url)
        if ok and os.path.isfile(dest_path):
            duration = int(time.time() - start_time)
            size_mb = round(os.path.getsize(dest_path) / 1024 / 1024, 1)
            log_daemon(f"下载成功: {os.path.basename(dest_path)}，{size_mb}MB，{duration}s")
            report_event("download_success",
                         {"version": tag, "duration": duration, "size_mb": size_mb,
                          "attempt": attempt + 1})
            return True
        log_daemon(f"aria2 下载失败（第 {attempt + 1} 轮）")
        report_event("download_failure",
                     {"version": tag, "attempt": attempt + 1, "mirrors": len(urls)})
        if attempt < DOWNLOAD_RETRY - 1:
            time.sleep(15)
    set_daemon_status("idle", 0, "下载失败，稍后重试")
    return False


# ── 更新检查 ──────────────────────────────────────────
def _http_json(url: str, timeout: int = 10, headers: dict = None,
               label: str = "") -> object | None:
    """取 JSON。失败返回 None，但**一定记日志**。

    Accept 头以前写的是 `application/vnd.github+json`（GitHub 专用媒体类型），
    发给 Supabase 的 PostgREST 会被判 406：
        {"code":"PGRST107","message":"None of these media types are available:
          application/vnd.github+json"}
    而这里原来把异常整个吞掉 —— 于是"更新检查"几年如一日地静默失败，
    界面还显示"当前已是最新版本"（beta29 实测：装着的版本坚信自己是最新的）。
    GitHub 的 REST API 同样接受 `application/json`，所以统一用它。
    """
    host = ""
    for scheme in ("https://", "http://"):
        if url.startswith(scheme):
            host = url[len(scheme):].split("/", 1)[0]
            break
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "idiot-launch-updater",
                     "Accept": "application/json", **(headers or {})})
        with urllib.request.urlopen(
                req, timeout=timeout, context=ssl.create_default_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        log_daemon(f"{label or 'HTTP'} 失败 {host}: HTTP {e.code} {e.reason} {body}")
    except Exception as e:
        log_daemon(f"{label or 'HTTP'} 失败 {host}: {type(e).__name__}: {e}")
    return None


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}


def _github_json(url: str, timeout: int = 10) -> object | None:
    """GitHub API。带 token 失败（401/403，比如打包时塞进去的临时 token 早就过期）
    就**不带 token 再来一次** —— 未认证每小时 60 次，够几小时查一回了，
    总比彻底查不到强。
    """
    headers = _auth_headers()
    data = _http_json(url, timeout=timeout, headers=headers, label="GitHub API")
    if data is None and headers:
        log_daemon("GitHub API 带 token 失败，改用未认证重试")
        data = _http_json(url, timeout=timeout, label="GitHub API(无 token)")
    return data


# 上一次"查更新"的过程结果。界面必须能区分"确实是最新的"和"根本没查成"——
# beta29 的实测教训：查不到也显示"当前已是最新版本"，用户被这句话骗了很久。
_last_check = {"ok": None, "detail": ""}


def last_check_result() -> dict:
    """{ok: True/False/None, detail: str}。None 表示这次进程还没查过。"""
    return dict(_last_check)


def _mark_check(ok: bool | None, detail: str = "") -> None:
    _last_check["ok"] = None if ok is None else bool(ok)
    _last_check["detail"] = detail


def _get_latest_tag_via_redirect(repo: str) -> str | None:
    """GitHub API 限流时用 302 重定向拿最新 tag（不限流）。"""
    try:
        req = urllib.request.Request(
            f"https://github.com/{repo}/releases/latest",
            headers={"User-Agent": "idiot-launch-updater"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            final = resp.geturl()
        import re

        m = re.search(r"/releases/tag/([^/]+)$", final)
        if m:
            return m.group(1).lstrip("vV")
    except Exception as e:
        log_daemon(f"GitHub 重定向取版本失败: {type(e).__name__}")
    return None


def get_latest_launcher_info() -> dict | None:
    """查最新版本。

    返回 None 有两种完全不同的含义：**确实是最新的**，或者**根本没查成**。
    调用方要用 `last_check_result()` 区分（界面必须说实话）。
    """
    _mark_check(None)  # 先当成"没查成"，查到结果再翻过来
    current_is_beta = is_beta_version(LAUNCHER_VERSION)

    # 方案 1：Supabase（不限流，优先）
    #
    # beta 版要能升到**正式版**，所以 beta 版查"所有渠道的 is_latest"再挑版本号最高的；
    # 正式版只认 stable（正式版用户不该被拉去装 beta）。
    # 历史教训：以前 beta 版只查 channel=beta，于是正式版一发出来，
    # beta 装机版查询返回的还是它自己那条 beta 记录 → 判成"已是最新"，
    # 永远升不到正式版。
    try:
        query = ("is_latest=eq.true" if current_is_beta
                 else "channel=eq.stable&is_latest=eq.true")
        url = (f"{SUPABASE_URL}/rest/v1/latest_version?{query}"
               f"&select=version,download_url,sha256,release_notes")
        data = _http_json(url, timeout=8, headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }, label="Supabase 版本查询")
        if isinstance(data, list) and data:
            best = None
            for row in data:
                if not isinstance(row, dict):
                    continue
                row_version = str(row.get("version", ""))
                if not row_version:
                    continue
                if not current_is_beta and is_beta_version(row_version):
                    continue
                if best is None or compare_versions(
                        row_version, str(best.get("version", ""))) > 0:
                    best = row
            if best is not None:
                version = str(best.get("version", ""))
                if compare_versions(version, LAUNCHER_VERSION) > 0:
                    _mark_check(True, "有新版本")
                    return {
                        "version": version,
                        "url": best.get("download_url", ""),
                        "size": 0,
                        "name": f"{LAUNCHER_SETUP_PREFIX}{version}.exe",
                        "release_notes": best.get("release_notes", ""),
                        "sha256": best.get("sha256", ""),
                    }
                _mark_check(True, "已是最新")
                return None  # Supabase 有数据但已是最新（不再打 GitHub API）
        if isinstance(data, list):
            log_daemon(f"Supabase 里没有可用的最新版本记录（查询: {query}）")
    except Exception as e:
        log_daemon(f"Supabase 查询异常: {type(e).__name__}: {e}")

    # 方案 2：GitHub /tags
    tags = _github_json(LAUNCHER_TAGS_API, timeout=10)
    if isinstance(tags, list):
        best_tag, best_version = None, None
        for t in tags:
            if not isinstance(t, dict):
                continue
            version = str(t.get("name", "")).lstrip("vV")
            if not version or compare_versions(version, LAUNCHER_VERSION) <= 0:
                continue
            if not current_is_beta and is_beta_version(version):
                continue
            if best_version is None or compare_versions(version, best_version) > 0:
                best_version, best_tag = version, t.get("name")
        if best_tag and best_version:
            rel = _github_json(
                f"https://api.github.com/repos/tgcz2011/idiot-launch/releases/tags/{best_tag}",
                timeout=10)
            expected = f"{LAUNCHER_SETUP_PREFIX}{best_version}.exe"
            if isinstance(rel, dict):
                for asset in rel.get("assets", []) or []:
                    if asset.get("name") == expected:
                        return {
                            "version": best_version,
                            "url": asset["browser_download_url"],
                            "size": asset.get("size", 0),
                            "name": expected,
                            "release_notes": rel.get("body", ""),
                            "sha256": asset.get("digest", ""),
                        }
            # release 查不到就按命名规则直接拼下载地址
            _mark_check(True, "有新版本")
            return {
                "version": best_version, "size": 0, "name": expected,
                "url": (f"https://github.com/tgcz2011/idiot-launch/releases/download/"
                        f"{best_tag}/{expected}"),
                "release_notes": "", "sha256": "",
            }
        _mark_check(True, "已是最新")

    # 方案 3：/releases（beta 版需要）
    if current_is_beta:
        releases = _github_json(
            "https://api.github.com/repos/tgcz2011/idiot-launch/releases?per_page=20",
            timeout=10)
        if isinstance(releases, list):
            for rel in releases:
                if not isinstance(rel, dict) or rel.get("draft"):
                    continue
                version = str(rel.get("tag_name", "")).lstrip("vV")
                if not version or compare_versions(version, LAUNCHER_VERSION) <= 0:
                    continue
                expected = f"{LAUNCHER_SETUP_PREFIX}{version}.exe"
                for asset in rel.get("assets", []) or []:
                    if asset.get("name") == expected:
                        _mark_check(True, "有新版本")
                        return {
                            "version": version,
                            "url": asset["browser_download_url"],
                            "size": asset.get("size", 0),
                            "name": expected,
                            "release_notes": rel.get("body", ""),
                            "sha256": asset.get("digest", ""),
                        }
                break
            _mark_check(True, "已是最新")

    # 方案 4：302 重定向（仅正式版）
    if not current_is_beta:
        version = _get_latest_tag_via_redirect("tgcz2011/idiot-launch")
        if version and compare_versions(version, LAUNCHER_VERSION) > 0:
            _mark_check(True, "有新版本")
            name = f"{LAUNCHER_SETUP_PREFIX}{version}.exe"
            return {
                "version": version, "size": 0, "name": name,
                "url": (f"https://github.com/tgcz2011/idiot-launch/releases/download/"
                        f"v{version}/{name}"),
                "release_notes": "", "sha256": "",
            }
        if version:
            _mark_check(True, "已是最新")

    # 走到这里还没定论 = 所有渠道都没连上。绝不能当成"已是最新"报给用户。
    if _last_check["ok"] is None:
        _mark_check(False, "连不上更新服务器")
        log_daemon("更新检查：所有渠道都失败（详见上面的失败原因）")
    return None


def _cleanup_stale_launcher_pending(state: dict) -> dict:
    path = state.get("pending_launcher_path")
    version = state.get("pending_launcher_version")
    if path and version and compare_versions(version, LAUNCHER_VERSION) <= 0:
        _remove_installer(path)
        state.pop("pending_launcher_path", None)
        state.pop("pending_launcher_version", None)
        state.pop("launcher_download", None)
        save_state(state)
    return state


def pending_update_info() -> dict | None:
    """已下载好、可以直接安装的更新。"""
    with _state_lock:
        state = _cleanup_stale_launcher_pending(load_state())
    path = state.get("pending_launcher_path")
    version = state.get("pending_launcher_version")
    if not path or not version or not os.path.isfile(path):
        return None
    if os.path.getsize(path) < LAUNCHER_MIN_SIZE:
        return None
    if compare_versions(version, LAUNCHER_VERSION) <= 0:
        return None
    return {"version": version, "path": path,
            "size": os.path.getsize(path),
            "release_notes": state.get("launcher_release_notes", "")}


def has_pending_launcher_update() -> bool:
    return pending_update_info() is not None


# ── 下载线程 ──────────────────────────────────────────
_launcher_download_thread = None
_launcher_download_lock = threading.Lock()


def _launcher_download_worker(url: str, dest: str, version: str,
                              release_notes: str, expected_sha256: str = "") -> None:
    def _on_progress(percent):
        set_download_state(version, percent, "downloading", dest, release_notes)

    set_download_state(version, 0.0, "downloading", dest, release_notes)

    ok = download_installer(url, dest, tag="launcher", on_progress=_on_progress)
    if not ok:
        with _state_lock:
            st = load_state()
            st["download_failures"] = int(st.get("download_failures", 0)) + 1
            st["download_failed_at"] = time.time()
            save_state(st)
        # 状态必须改成 failed：留在 downloading 界面就会一直显示"下载中 0%"
        set_download_state(version, 0.0, "failed", dest, release_notes)
        set_daemon_status("idle", 0, "更新下载失败，稍后重试")
        return

    if not os.path.isfile(dest) or os.path.getsize(dest) < LAUNCHER_MIN_SIZE:
        _remove_installer(dest)
        set_download_state(version, 0.0, "failed", dest, release_notes)
        set_daemon_status("idle", 0, "下载文件不完整，已删除")
        return

    if not verify_sha256(dest, expected_sha256):
        log_daemon(f"SHA-256 校验失败，删除安装包: {os.path.basename(dest)}")
        set_download_state(version, 0.0, "failed", dest, release_notes)
        set_daemon_status("idle", 0, "更新包校验失败，已拒绝更新，将重新下载")
        _remove_installer(dest)
        return

    if compare_versions(version, LAUNCHER_VERSION) <= 0:
        log_daemon(f"下载完成但当前已是 v{LAUNCHER_VERSION}，跳过")
        _remove_installer(dest)
        clear_download_state(f"下载到的 v{version} 不高于当前版本")
        set_daemon_status("idle", 0, "已是最新版本")
        return

    with _state_lock:
        st = load_state()
        st["pending_launcher_path"] = dest
        st["pending_launcher_version"] = version
        st["launcher_release_notes"] = release_notes
        st["download_failures"] = 0
        save_state(st)
    set_download_state(version, 100.0, "complete", dest, release_notes)
    set_daemon_status("idle", 0, f"已下载 v{version}，可一键更新")
    log_daemon(f"v{version} 下载完成（SHA-256 通过），等待安装")
    notify_tray("更新已就绪", f"傻瓜启动器 v{version} 已下载完成，可一键更新。")
    from src.telemetry import report_event

    report_event("update_ready", {"from_version": LAUNCHER_VERSION, "to_version": version})


def _check_and_download_launcher_update() -> None:
    """检查并（如需要）后台下载更新包。

    注意：**不**受"自动更新"开关影响 —— 那个开关只控制"空闲时自动安装"。
    关掉它以后仍然会后台下载，这样用户点「一键更新」时是立即可用的
    （设置页的文案就是这么写的）。
    """
    global _launcher_download_thread
    if not getattr(sys, "frozen", False):
        return

    with _state_lock:
        state = _cleanup_stale_launcher_pending(load_state())
        # 用户点"检查更新"时置的强制标记（消费掉，但不影响 last_check 时间戳）
        force = bool(state.pop("force_check", False))
        if force:
            save_state(state)

    if pending_update_info():
        return

    now = time.time()
    # 连续下载失败时退避，避免在断网的教室网络里一直空转。
    # 用户手动点"检查更新/重试"时（force）不受退避限制。
    failures = int(state.get("download_failures", 0))
    if not force and failures >= MAX_DOWNLOAD_FAILURES:
        backoff = min(6 * 3600, 600 * failures)
        if now - state.get("download_failed_at", 0) < backoff:
            return

    if not force and now - state.get("launcher_last_check", 0) < CHECK_INTERVAL:
        return
    if _launcher_download_thread and _launcher_download_thread.is_alive():
        return

    set_daemon_status("checking", 0, "正在检查更新...")
    t0 = time.time()
    latest = get_latest_launcher_info()
    check = last_check_result()
    duration = round(time.time() - t0, 1)
    outcome = ("有新版本 " + latest["version"]) if latest else (
        "无新版本" if check.get("ok") else f"检查失败（{check.get('detail') or '未知原因'}）")
    log_daemon(f"更新检查完成 {duration}s: {outcome}")

    from src.telemetry import report_event

    report_event("update_check", {
        "has_update": bool(latest),
        "latest_version": latest["version"] if latest else None,
        "duration": duration,
        "check_ok": check.get("ok"),
    })

    with _state_lock:
        st = load_state()
        st["launcher_last_check"] = now
        # 每次检查都刷新：没有新版本时清掉，否则界面会一直说有新版本
        st["latest_seen_version"] = latest["version"] if latest else ""
        # 查成没查成也要存下来：界面不能再把"没查成"说成"已是最新"
        st["launcher_check_ok"] = check.get("ok")
        st["launcher_check_detail"] = check.get("detail", "")
        save_state(st)

    if not latest:
        if check.get("ok"):
            set_daemon_status("idle", 0, "已是最新版本")
        else:
            set_daemon_status("idle", 0,
                              f"检查更新失败：{check.get('detail') or '连不上更新服务器'}")
        return

    dest = os.path.join(UPDATE_DIR, f"{LAUNCHER_SETUP_PREFIX}{latest['version']}.exe")
    if os.path.isfile(dest) and not os.path.isfile(dest + ".aria2"):
        if (os.path.getsize(dest) >= LAUNCHER_MIN_SIZE
                and verify_sha256(dest, latest.get("sha256", ""))):
            with _state_lock:
                st = load_state()
                st["pending_launcher_path"] = dest
                st["pending_launcher_version"] = latest["version"]
                st["launcher_release_notes"] = latest.get("release_notes", "")
                save_state(st)
            return
        log_daemon("已有安装包校验失败，删除后重新下载")
        _remove_installer(dest)

    log_daemon(f"发现新版本 {latest['version']}，后台下载")
    with _launcher_download_lock:
        if _launcher_download_thread and _launcher_download_thread.is_alive():
            return
        _launcher_download_thread = threading.Thread(
            target=_launcher_download_worker,
            args=(latest["url"], dest, latest["version"],
                  latest.get("release_notes", ""), latest.get("sha256", "")),
            daemon=True, name="launcher-update-download")
        _launcher_download_thread.start()


# ── 安装更新（不再使用 VBS） ───────────────────────────
# 旧方案用 wscript + VBS 脚本替换文件，问题是：
#   1) 脚本是 daemon 的子进程，安装包里的 taskkill /T 会把脚本自己一起杀掉，
#      结果 result 文件永远停在 status=running，校验/重启/清理全部不执行；
#   2) 静默安装完全没有界面，被 SmartScreen 拦下时用户什么都看不到。
# 现在直接调安装包本身：
#   * 用户点"一键更新" → /SILENT（安装包自带进度条，看得见）
#   * 空闲自动更新     → /VERYSILENT（完全无窗口）
#   * /AutoUpdate=1 让安装脚本在装完后自动把程序重新拉起来
#   * 启动安装包后立刻 os._exit，避免自己占着文件让安装失败
INSTALLER_COMMON_FLAGS = ["/SUPPRESSMSGBOXES", "/NORESTART", "/AutoUpdate=1"]


def start_update_installer(installer: str, silent: bool = False) -> bool:
    """启动安装包。silent=True 完全无界面，False 显示安装包自带的进度条。"""
    if not installer or not os.path.isfile(installer):
        return False
    mode = "/VERYSILENT" if silent else "/SILENT"
    try:
        proc = subprocess.Popen(
            [installer, mode, *INSTALLER_COMMON_FLAGS],
            creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | NEW_PROCESS_GROUP
            close_fds=True,
        )
    except Exception as e:
        log_daemon(f"启动更新安装包失败: {type(e).__name__}: {e}")
        return False

    log_daemon(f"更新安装包已启动（{mode}）: {os.path.basename(installer)}")
    # 给安装包 2 秒确认还活着：被安全软件拦掉/参数错误会立刻退出
    for _ in range(20):
        time.sleep(0.1)
        if proc.poll() is not None:
            if proc.returncode != 0:
                log_daemon(f"安装包异常退出，返回码 {proc.returncode}，放弃本次更新")
                return False
            break
    return True


def exit_for_update() -> None:
    """安装包需要独占文件，必须让整个进程（所有线程）立刻退出。"""
    from src.telemetry import report_event, flush

    try:
        report_event("update_install", {
            "from_version": LAUNCHER_VERSION,
            "to_version": load_state().get("pending_launcher_version", "?"),
        })
        flush(timeout=2.0)
    except Exception:
        pass
    log_daemon("退出当前进程，交由安装包完成更新")
    os._exit(0)


def apply_launcher_update_if_pending(force: bool = False) -> bool:
    """有待更新的安装包时启动它。返回 True 表示调用方应立即退出。

    force=True：用户点击「一键更新」→ 立即执行
    force=False：daemon 循环调用 → 只有连续 3 次确认空闲才执行
    """
    if not getattr(sys, "frozen", False):
        return False
    info = pending_update_info()
    if not info:
        return False

    if not force:
        if not is_auto_update_enabled():
            return False
        threshold = idle_threshold_seconds()
        idle_ok = True
        for _ in range(3):
            if get_idle_seconds() < threshold:
                idle_ok = False
                break
            time.sleep(2)
        if not idle_ok:
            return False
        log_daemon(f"空闲确认通过，静默更新到 v{info['version']}")
        set_daemon_status("updating", 0, f"正在静默更新到 v{info['version']}...")
        silent = True
        notify_tray("正在自动更新", f"傻瓜启动器将更新到 v{info['version']}，屏幕可能闪一下。")
    else:
        log_daemon(f"用户触发一键更新到 v{info['version']}")
        set_daemon_status("updating", 0, f"正在更新到 v{info['version']}...")
        silent = False

    if not start_update_installer(info["path"], silent=silent):
        set_daemon_status("idle", 0, "更新程序启动失败，可稍后重试")
        return False
    return True


def apply_launcher_update_now() -> bool:
    return apply_launcher_update_if_pending(force=True)


def apply_launcher_update_idle() -> bool:
    return apply_launcher_update_if_pending(force=False)


# ── daemon ────────────────────────────────────────────
def signal_daemon_quit() -> bool:
    event = _event_open(DAEMON_QUIT_EVENT)
    if not event:
        return False
    try:
        _kernel32.SetEvent(event)
        return True
    finally:
        _kernel32.CloseHandle(event)


def _handle_daemon_command(cmd: dict) -> None:
    action = cmd.get("cmd", "")
    log_daemon(f"收到命令: {action}")
    if action == "check_updates":
        # 只置"强制检查"标记，**不要**把 launcher_last_check 清零：
        # 清零会让界面立刻变成"还没有检查过更新"（用户反馈过的现象）。
        update_state({"force_check": True})
        set_daemon_status("checking", 0, "正在手动检查更新...")
    elif action == "apply_launcher_update_now":
        # 由 API 层负责退出进程，这里只启动安装包
        if apply_launcher_update_now():
            log_daemon("一键更新已启动")


def _create_shortcut(target: str, shortcut_path: str, icon_path: str = "",
                     description: str = "") -> bool:
    """创建 .lnk。优先 pywin32（不弹窗），失败再退到 PowerShell。"""
    try:
        import pythoncom
        from win32com.client import Dispatch

        pythoncom.CoInitialize()
        try:
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortcut(shortcut_path)
            shortcut.TargetPath = target
            shortcut.WorkingDirectory = os.path.dirname(target)
            if icon_path:
                shortcut.IconLocation = f"{icon_path},0"
            if description:
                shortcut.Description = description
            shortcut.Save()
            if os.path.isfile(shortcut_path):
                return True
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:
        log_daemon(f"pywin32 创建快捷方式失败({shortcut_path}): {type(e).__name__}")

    # 兜底：PowerShell。路径用单引号包裹并转义，避免中文/引号路径出错。
    def _q(p: str) -> str:
        return "'" + p.replace("'", "''") + "'"

    try:
        script = (
            "$ws = New-Object -ComObject WScript.Shell\n"
            f"$s = $ws.CreateShortcut({_q(shortcut_path)})\n"
            f"$s.TargetPath = {_q(target)}\n"
            f"$s.WorkingDirectory = {_q(os.path.dirname(target))}\n"
        )
        if icon_path:
            script += f"$s.IconLocation = {_q(icon_path + ',0')}\n"
        if description:
            script += f"$s.Description = {_q(description)}\n"
        script += "$s.Save()\n"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            capture_output=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        return result.returncode == 0 and os.path.isfile(shortcut_path)
    except Exception as e:
        log_daemon(f"创建快捷方式失败({shortcut_path}): {type(e).__name__}: {e}")
        return False


def ensure_shortcuts() -> None:
    """保证 D 盘根目录 + 桌面（优先公共桌面）各有一个快捷方式。

    注意：这是作者有意为之的"流氓软件模式"（见 README），用于对抗冰点还原，
    不是 bug —— 老师/管理员删掉图标后 30 秒内会被重建。
    """
    if not getattr(sys, "frozen", False):
        return
    target = LAUNCHER_INSTALL_EXE if os.path.isfile(LAUNCHER_INSTALL_EXE) else sys.executable
    if not os.path.isfile(target):
        return
    locations = []
    if os.path.isdir("D:\\"):
        locations.append(r"D:\傻瓜启动器.lnk")
    public_desktop = r"C:\Users\Public\Desktop"
    user_desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    if os.path.isdir(public_desktop):
        locations.append(os.path.join(public_desktop, "傻瓜启动器.lnk"))
    elif os.path.isdir(user_desktop):
        locations.append(os.path.join(user_desktop, "傻瓜启动器.lnk"))

    for lnk in locations:
        try:
            if os.path.isfile(lnk):
                continue
            if _create_shortcut(target, lnk, target, "傻瓜启动器 - 教室倒计时一键启动"):
                try:
                    subprocess.run(
                        ["ie4uinit.exe", "-show"], capture_output=True, timeout=5,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
                except Exception:
                    pass
        except Exception as e:
            log_daemon(f"创建快捷方式异常({lnk}): {type(e).__name__}: {e}")


# 托盘气泡通知（由 backend_server 注入实现）
_notifier = None


def set_notifier(fn) -> None:
    global _notifier
    _notifier = fn


def notify_tray(title: str, message: str) -> None:
    try:
        if _notifier:
            _notifier(title, message)
    except Exception:
        pass


def daemon_run() -> int:
    """后台守护主循环。整个函数只在"进程级单实例"下运行。"""
    mutex = _mutex_acquire(DAEMON_MUTEX)
    if mutex is None:
        log_daemon("daemon 已在运行，退出")
        return 0
    log_daemon(f"daemon 启动 (pid={os.getpid()}, v{LAUNCHER_VERSION})")

    set_daemon_status("starting", 0, "守护进程启动")
    from src.telemetry import report_event

    report_event("app_launch", {
        "pid": os.getpid(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "auto_update": is_auto_update_enabled(),
    })

    quit_event = _event_create(DAEMON_QUIT_EVENT)

    # 上一次下载可能被"退出程序 / 安装更新 / 断网"打断，留下半截 downloading 状态，
    # 界面就会一直显示"正在后台下载 0%"（用户实测反馈）。启动先收拾干净。
    try:
        _clear_stale_download_on_start()
    except Exception as e:
        log_daemon(f"清理下载状态失败: {type(e).__name__}: {e}")

    # 启动后 10 分钟内已经检查过就不再重复检查（避免频繁开关程序刷接口）。
    # 同样只置 force_check、不清零时间戳，否则界面会短暂显示"还没有检查过更新"。
    with _state_lock:
        st = load_state()
        if time.time() - st.get("launcher_last_check", 0) > STARTUP_CHECK_GRACE:
            st["force_check"] = True
        save_state(st)

    _last_cleanup = 0.0
    _morning_periods_last_check = 0.0
    try:
        while True:
            try:
                ensure_shortcuts()

                now = time.time()
                if now - _last_cleanup > 3600:
                    _last_cleanup = now
                    keep = ""
                    info = pending_update_info()
                    if info:
                        keep = os.path.basename(info["path"])
                    else:
                        # 正在下载的安装包绝不能被当成"旧安装包"删掉
                        inflight = _current_download_installer()
                        if inflight:
                            keep = os.path.basename(inflight)
                    cleanup_stale_downloads(keep_path=keep)

                if now - _morning_periods_last_check > 600:
                    _morning_periods_last_check = now
                    refresh_morning_periods()

                cmd = poll_command()
                if cmd:
                    _handle_daemon_command(cmd)

                if apply_launcher_update_idle():
                    exit_for_update()

                _check_and_download_launcher_update()

                # 下载线程还活着就把状态时间戳往后推（慢网络下进度可能长时间不动）
                if _launcher_download_thread and _launcher_download_thread.is_alive():
                    touch_download_state()

                activity = load_state().get("daemon", {}).get("activity", "")
                if activity not in ("downloading", "updating", "installing", "waiting", "checking"):
                    set_daemon_status("idle", 0, get_daemon_status_detail())

                for _ in range(6):
                    if _wait_event(quit_event, 5000):
                        log_daemon("收到退出事件，daemon 优雅退出")
                        return 0
                    cmd = poll_command()
                    if cmd:
                        _handle_daemon_command(cmd)
                        activity = load_state().get("daemon", {}).get("activity", "")
                        if activity not in ("downloading", "updating", "installing",
                                            "waiting", "checking"):
                            set_daemon_status("idle", 0, get_daemon_status_detail())
            except Exception as e:
                log_daemon(f"daemon 主循环异常: {type(e).__name__}: {e}")
                set_daemon_status("idle", 0, f"守护进程异常恢复: {type(e).__name__}")
                time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        set_daemon_status("stopped", 0, "守护进程已停止")
        log_daemon("daemon 退出")
        if quit_event:
            try:
                _kernel32.CloseHandle(quit_event)
            except Exception:
                pass
        if mutex:
            try:
                _kernel32.CloseHandle(mutex)
            except Exception:
                pass
    return 0


def get_daemon_status_detail() -> str:
    info = pending_update_info()
    if info:
        return f"v{info['version']} 已下载，可一键更新"
    return "后台运行中"


# ── 其它工具 ──────────────────────────────────────────
def disk_free_gb(path: str = LAUNCHER_INSTALL_DIR) -> float | None:
    try:
        return round(shutil.disk_usage(path).free / 1024 ** 3, 1)
    except Exception:
        try:
            return round(shutil.disk_usage(os.path.splitdrive(path)[0] + "\\").free
                         / 1024 ** 3, 1)
        except Exception:
            return None


def open_folder(path: str) -> bool:
    try:
        os.startfile(path)  # noqa: S606 - 仅用于打开本地已知目录
        return True
    except Exception:
        return False


def launcher_install_exists() -> bool:
    return os.path.isfile(LAUNCHER_INSTALL_EXE)


def data_dir() -> str:
    return UPDATE_DIR


__all__ = [
    "APP_NAME", "LAUNCHER_VERSION", "UPDATE_DIR", "SETTINGS_FILE",
    "load_settings", "save_settings", "is_telemetry_enabled", "is_auto_update_enabled",
    "parse_version", "compare_versions", "is_beta_version",
    "log_daemon", "load_state", "save_state", "update_state",
    "set_daemon_status", "get_daemon_status", "send_command", "poll_command",
    "set_download_state", "clear_download_state", "get_download_state",
    "launch_countdown", "launch_custom", "launch_settings",
    "is_running", "quit_countdown",
    "load_morning_config", "save_morning_config", "is_morning_logged_in",
    "verify_morning_login", "get_morning_students", "open_morning_reading",
    "refresh_morning_periods",
    "get_latest_launcher_info", "pending_update_info", "has_pending_launcher_update",
    "start_update_installer", "exit_for_update",
    "apply_launcher_update_if_pending", "apply_launcher_update_now",
    "apply_launcher_update_idle", "cleanup_stale_downloads",
    "daemon_run", "signal_daemon_quit", "set_notifier", "notify_tray",
    "ensure_shortcuts", "disk_free_gb", "open_folder", "data_dir",
    "launcher_install_exists", "get_file_version", "get_installed_version",
]


def get_file_version(path: str) -> str | None:
    """读任意 exe 的 FileVersion（a.b.c.d），失败返回 None。"""
    if not path or not os.path.isfile(path):
        return None
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if size <= 0:
            return None
        res = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(path, None, size, res)
        val = ctypes.c_void_p()
        length = ctypes.c_uint()
        if ctypes.windll.version.VerQueryValueW(res, "\\", ctypes.byref(val), ctypes.byref(length)):
            class VS_FIXEDFILEINFO(ctypes.Structure):
                _fields_ = [("dwSignature", ctypes.c_uint32), ("dwStrucVersion", ctypes.c_uint32),
                            ("dwFileVersionMS", ctypes.c_uint32), ("dwFileVersionLS", ctypes.c_uint32),
                            ("dwProductVersionMS", ctypes.c_uint32), ("dwProductVersionLS", ctypes.c_uint32)]

            info = ctypes.cast(val, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
            return "{}.{}.{}.{}".format(
                (info.dwFileVersionMS >> 16) & 0xFFFF, info.dwFileVersionMS & 0xFFFF,
                (info.dwFileVersionLS >> 16) & 0xFFFF, info.dwFileVersionLS & 0xFFFF)
    except Exception:
        return None


def get_installed_version() -> str | None:
    """已安装的启动器版本（读 PE 版本号）。"""
    return get_file_version(LAUNCHER_INSTALL_EXE)
