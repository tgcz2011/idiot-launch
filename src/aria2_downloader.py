"""
aria2 下载模块
通过 JSON-RPC 控制 aria2c，支持多源下载、分块、实时进度
"""
import json
import os
import random
import socket
import subprocess
import tempfile
import time
import urllib.request


def _find_aria2c():
    """查找 aria2c.exe 路径"""
    # 打包后：在 exe 同目录的 assets 下
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        candidates = [
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
    import sys
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
