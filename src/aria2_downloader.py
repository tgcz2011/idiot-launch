"""
aria2 下载模块
通过 JSON-RPC 控制 aria2c，支持多源下载、分块、实时进度。

孤儿进程问题（历史隐患）：
  后端退出走的是 os._exit(0)（退出程序 / 装更新），它会绕过所有 finally，
  于是这里 terminate aria2c 的代码根本不会执行 —— 结果 D 盘后台留着一个
  没人管的 aria2c 继续下载；下次启动又起一个去写同一个文件。
  现在把 aria2c 放进一个 "kill-on-job-close" 的 Job Object：
  本进程一消失（无论怎么消失），Windows 自动关掉 job 句柄 → aria2c 被杀。
  另外把 pid 落到 aria2.pid，启动时兜底清理上一次可能残留的 aria2c。
"""
import ctypes
import json
import os
import random
import socket
import subprocess
import time
import urllib.request

PID_FILE_NAME = "aria2.pid"


def _find_aria2c():
    """查找 aria2c.exe 路径"""
    import sys
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        candidates = [
            os.path.join(base, "_internal", "assets", "aria2c.exe"),
            os.path.join(base, "assets", "aria2c.exe"),
            os.path.join(base, "aria2c.exe"),
        ]
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(base, "assets", "aria2c.exe"),
        ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _free_port():
    """获取一个空闲端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _rpc_call(port, secret, method, params=None):
    """调用 aria2 JSON-RPC"""
    url = f"http://127.0.0.1:{port}/jsonrpc"
    payload = {
        "jsonrpc": "2.0",
        "id": str(random.randint(1, 999999)),
        "method": method,
        "params": [f"token:{secret}"] + (params or []),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        if "error" in result:
            raise Exception(f"aria2 RPC error: {result['error']}")
        return result.get("result")


# ── Win32 Job Object：父进程一死就带走 aria2c ──────────────────────────────
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _create_kill_on_close_job(pid):
    """把 pid 放进 kill-on-job-close 的 Job Object，返回 job 句柄；失败返回 None。

    只要本进程持有这个句柄，本进程一旦结束（含 os._exit），句柄被系统回收，
    job 关闭 → job 里的 aria2c 被一起杀掉。父进程无需任何清理代码。
    """
    if os.name != "nt":
        return None
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = ctypes.c_void_p
        k32.OpenProcess.restype = ctypes.c_void_p
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(
                ctypes.c_void_p(job), _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info), ctypes.sizeof(info)):
            k32.CloseHandle(ctypes.c_void_p(job))
            return None
        ph = k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, int(pid))
        if not ph:
            k32.CloseHandle(ctypes.c_void_p(job))
            return None
        try:
            ok = k32.AssignProcessToJobObject(ctypes.c_void_p(job), ctypes.c_void_p(ph))
        finally:
            k32.CloseHandle(ctypes.c_void_p(ph))
        if not ok:
            k32.CloseHandle(ctypes.c_void_p(job))
            return None
        return job
    except Exception:
        return None


def _close_job(job):
    if not job or os.name != "nt":
        return
    try:
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(ctypes.c_void_p(job))
    except Exception:
        pass


def _pid_file(directory):
    return os.path.join(directory, PID_FILE_NAME)


def _image_name_of(pid):
    """取进程映像名（不含路径），取不到返回 ''。"""
    if os.name != "nt":
        return ""
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_uint(1024)
            if k32.QueryFullProcessImageNameW(ctypes.c_void_p(h), 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
            return ""
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))
    except Exception:
        return ""


def kill_orphan_aria2(directory):
    """清理上一次残留的 aria2c（崩溃 / os._exit 留下）。

    只杀 pid 文件里记录、且映像名确实是 aria2c.exe 的进程 —— 绝不按名字盲杀，
    免得误伤用户自己装的 aria2。
    """
    path = _pid_file(directory)
    try:
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            pid = int((f.read() or "0").strip())
        if pid > 0 and _image_name_of(pid).lower() == "aria2c.exe":
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def download_with_aria2(urls, output_path, progress_callback=None, timeout=900):
    """
    使用 aria2 下载文件

    Args:
        urls: 下载 URL 列表（多源）
        output_path: 输出文件路径
        progress_callback: 进度回调函数 callback(percent, speed_bytes_per_sec)
        timeout: 超时时间（秒）

    Returns:
        bool: 是否成功
    """
    aria2c = _find_aria2c()
    if not aria2c:
        return False

    port = _free_port()
    secret = f"aria2_{random.randint(100000, 999999)}"
    output_dir = os.path.dirname(output_path)
    output_name = os.path.basename(output_path)
    os.makedirs(output_dir, exist_ok=True)

    # 启动 aria2c
    proc = subprocess.Popen(
        [
            aria2c,
            "--enable-rpc",
            f"--rpc-listen-port={port}",
            f"--rpc-secret={secret}",
            "--rpc-listen-all=false",
            "--dir", output_dir,
            "--out", output_name,
            "--file-allocation=none",
            "--continue=true",
            "--max-connection-per-server=16",
            "--split=16",
            "--min-split-size=1M",
            "--console-log-level=error",
            "--summary-interval=0",
            "--auto-file-renaming=false",
            "--allow-overwrite=true",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    # 关键：把 aria2c 交给 kill-on-close 的 job。父进程无论怎么死，它都跟着死。
    job = _create_kill_on_close_job(proc.pid)

    # pid 落盘（job 之外的第二道保险：下次启动时兜底清理）
    try:
        with open(_pid_file(output_dir), "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
    except OSError:
        pass

    try:
        # 等待 aria2 启动
        ready = False
        for _ in range(30):
            try:
                _rpc_call(port, secret, "aria2.getVersion")
                ready = True
                break
            except Exception:
                time.sleep(0.2)
        if not ready:
            return False

        # 添加下载任务
        gid = _rpc_call(port, secret, "aria2.addUri", [urls, {}])

        # 轮询进度
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                return False

            try:
                status = _rpc_call(port, secret, "aria2.tellStatus", [gid])
            except Exception:
                time.sleep(0.5)
                continue

            state = status.get("status", "")
            total_length = int(status.get("totalLength", 0))
            completed_length = int(status.get("completedLength", 0))
            download_speed = int(status.get("downloadSpeed", 0))

            if state == "complete":
                if progress_callback:
                    progress_callback(100, download_speed)
                return True
            elif state == "error":
                return False
            elif state == "removed":
                return False

            if total_length > 0 and progress_callback:
                percent = min(100, int(completed_length * 100 / total_length))
                progress_callback(percent, download_speed)

            time.sleep(0.5)

    finally:
        # 关闭 aria2
        try:
            _rpc_call(port, secret, "aria2.shutdown")
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        # 主动清掉 pid 文件；job 句柄最后关（关了就触发 kill-on-close）
        try:
            os.remove(_pid_file(output_dir))
        except OSError:
            pass
        _close_job(job)
