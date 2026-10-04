# -*- coding: utf-8 -*-
"""媒体源支持：网页 / 视频 / 图片 / 动图 统一走 Chromium 渲染。

- 远程 http(s) 源：直接使用。
- 本地文件：起 127.0.0.1 迷你 HTTP 服务（支持 Range，视频可拖动），
  WebView2 默认禁 file:// 访问，故必须走 http。
- 视频/图片/动图：生成内联 HTML（<video>/<img> 铺满黑底），交给同一渲染管线。
"""
import logging
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("media")

VIDEO_EXT = (".mp4", ".webm", ".m4v", ".mov", ".mkv", ".ogv")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".svg", ".ico")
ANIM_EXT = (".gif",)

_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{style}
</style></head><body>{body}</body></html>"""


def guess_kind(source: str) -> str:
    """page / video / image / anim"""
    low = source.lower().split("?", 1)[0]
    if low.endswith(VIDEO_EXT):
        return "video"
    if low.endswith(ANIM_EXT):
        return "anim"
    if low.endswith(IMAGE_EXT):
        return "image"
    return "page"


def build_html(kind: str, src: str, fit: str = "cover", mute: bool = True,
               loop: bool = True) -> str:
    """生成视频/图片渲染页。

    fit: cover=铺满裁剪 | contain=完整显示黑边 | fill=拉伸铺满
    mute/loop 仅对视频生效；视频静音时可直接自动播放，不静音时配合
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS 的 autoplay 放行策略。
    """
    import html as _html
    esc = _html.escape(src, quote=True)
    object_fit = {"contain": "contain", "fill": "fill"}.get(fit, "cover")
    bg = "#000"
    # 注意：这段用 % 格式化，CSS 花括号写单个；此前误用 {{ }} 导致样式非法被浏览器丢弃，
    # 视频/图片失去铺满样式缩在左上角（网页源不走此内联模板不受影响）
    style = ("html,body{margin:0;padding:0;width:100vw;height:100vh;"
             "background:%s;overflow:hidden}"
             "video,img{position:fixed;left:0;top:0;width:100vw;height:100vh;"
             "object-fit:%s}" % (bg, object_fit))
    if kind == "video":
        attrs = "autoplay loop" if loop else "autoplay"
        attrs += " muted" if mute else ""
        body = ('<video src="%s" %s playsinline '
                'onerror="document.body.innerHTML=\'<div style=color:#888;font:20px sans-serif;padding:40px>video load failed</div>\'">'
                '</video>') % (esc, attrs)
    else:  # image / anim
        body = '<img src="%s" alt="">' % esc
    return _PAGE.format(style=style, body=body)


class _FileHandler(BaseHTTPRequestHandler):
    file_path = ""

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = self.file_path
        size = os.path.getsize(path)
        start, end = 0, size - 1
        ranged = self.headers.get("Range")
        partial = False
        if ranged and ranged.startswith("bytes="):
            try:
                spec = ranged[6:].split(",")[0].strip()
                a, b = spec.split("-", 1)
                if not a:
                    # 后缀范围 "bytes=-500"：最后 500 字节。
                    # Chromium 读 MP4 尾部 moov 就用这种写法，之前被当成 0-500 返回，
                    # 结果本地 mp4 播不出来（黑屏）。
                    length = int(b)
                    length = min(length, size)
                    start = max(0, size - length)
                    end = size - 1
                else:
                    start = int(a)
                    end = int(b) if b else size - 1
                    end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.end_headers()
                    return
                partial = True
            except ValueError:
                start, end = 0, size - 1
                partial = False
        self.send_response(206 if partial else 200)
        ext = os.path.splitext(path)[1].lower()
        mime = {".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska",
                ".mov": "video/quicktime", ".m4v": "video/mp4", ".ogv": "video/ogg",
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
                ".svg": "image/svg+xml", ".ico": "image/x-icon"}.get(ext,
                                                                    "application/octet-stream")
        self.send_header("Content-Type", mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break  # 播放器主动断开是正常的
                left -= len(chunk)


class LocalSource:
    """为本地媒体文件提供 127.0.0.1 HTTP 服务（进程内常驻）。"""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        handler = type("H", (_FileHandler,), {"file_path": self.path})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        t = threading.Thread(target=self.server.serve_forever, daemon=True)
        t.start()
        name = urllib.parse.quote(os.path.basename(self.path))
        self.url = "http://127.0.0.1:%d/%s" % (self.port, name)
        log.info("local source serving %s at %s", self.path, self.url)


def resolve(source: str):
    """返回 (kind, final_src, local_or_None)。

    - http(s) 源直接使用；
    - 本地存在的文件：起 127.0.0.1 服务，返回实例需保活；
    - 域名样式的串补 https；
    - 路径样式但文件不存在：回退默认网页（避免黑屏）。
    """
    from . import config
    source = source.strip()
    if source.lower().startswith(("http://", "https://")):
        return guess_kind(source), source, None
    if os.path.isfile(source):
        local = LocalSource(source)
        return guess_kind(local.url), local.url, local
    # 只在"看起来真的是域名/网址"时才补 https。
    # 原来把 "video.mp4" 这种相对路径也补成 https://video.mp4，
    # 结果整屏显示 Chromium 的错误页。
    looks_like_host = ("." in source.split("/")[0]
                       and " " not in source
                       and not source.lower().endswith(
                           (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".gif",
                            ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".avi")))
    if looks_like_host and "\\" not in source:
        return guess_kind("https://" + source), "https://" + source, None
    log.warning("local source missing, fallback default: %s", source)
    return "page", config.DEFAULT_URL, None
