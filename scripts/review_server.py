# -*- coding: utf-8 -*-
"""Tiny local backend for the review HTML — enables two things a plain file:// page can't:

  1. Click a source unit in the page -> opens it READ-ONLY with the OS default viewer
     (files) or a file browser (folders).  GET /open?src=<relpath under SRC_ROOT>
  2. "提交待重分类" -> POST /reclassify-queue writes <name>_reclassify_queue.json next to the
     HTML, which scripts/reclassify.py then consumes.

It serves the built review HTML at `/` (re-read on every request, so after reclassify.py
rebuilds the page a simple browser refresh shows the merged result — no restart needed).

Everything it needs (source root, dataset name) is read from the HTML's embedded __META__,
so you only point it at the HTML.  Binds to 127.0.0.1 only.

    PYTHONIOENCODING=utf-8 python review_server.py [HTML] [PORT]
"""
import sys, os, json, re, threading, webbrowser, urllib.parse, subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ===== EDIT-ME (or pass argv: HTML PORT) ======================================
HTML = "./review.html"     # the built review page (from build_review_html.py)
PORT = 8765

def load_meta(html_path):
    """从已生成的审阅 HTML 页面中提取内嵌的 __META__ JSON 数据（name/srcRoot/dstRoot/big）。

    说明：
        build_review_html.py 生成页面时会把 meta 信息写进一个
        `<script id="metaData">...</script>` 标签，本函数用正则把该标签内的 JSON
        文本提取出来并解析成字典。找不到该标签时返回空字典 {}。

    参数：
        html_path (str): 审阅 HTML 文件路径。
    返回：
        dict: 解析出的 meta 信息（可能为空）。
    """
    txt = open(html_path, encoding="utf-8").read()
    m = re.search(r'id="metaData">(.*?)</script>', txt, re.S)
    meta = json.loads(m.group(1)) if m else {}
    return meta

def open_readonly(path):
    """用操作系统默认程序只读方式打开一个文件或文件夹（用于“点击源单元查看”功能）。

    说明：
        - Windows：调用 os.startfile 打开系统关联的默认查看器；
        - macOS：调用 `open` 命令；
        - 其他（Linux 等）：调用 `xdg-open` 命令。
        本函数只负责“打开查看”，不会修改或删除目标内容。
    """
    if os.name == "nt":
        os.startfile(path)                       # noqa: S606 - default viewer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])

def make_handler(html_path, src_root, queue_path):
    """构造并返回一个绑定了具体参数（html 路径/源目录根/队列文件路径）的 HTTP 请求处理器类。

    说明：
        之所以用一个工厂函数动态构造 Handler 类，是因为 http.server 的
        BaseHTTPRequestHandler 子类在实例化时不方便直接传参，这里通过闭包把
        html_path/src_root/queue_path 三个参数“捕获”进内部类 H 中，
        ThreadingHTTPServer 只需要一个类，不需要额外参数。

    参数：
        html_path (str): 要提供服务的审阅 HTML 文件路径。
        src_root (str): 源目录根路径（限制 /open 只能访问该目录下的内容）。
        queue_path (str): 待重分类队列 JSON 文件的写出路径。
    返回：
        type: 一个 BaseHTTPRequestHandler 子类 H，供 ThreadingHTTPServer 使用。
    """
    src_real = os.path.realpath(src_root)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass          # 静默：不在控制台打印每次请求的访问日志

        def _send(self, code, body=b"", ctype="text/plain; charset=utf-8"):
            """统一的响应发送辅助方法：写状态码、Content-Type、Content-Length 和响应体。"""
            if isinstance(body, str): body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body: self.wfile.write(body)

        def do_GET(self):
            """处理 GET 请求，支持三个路径：

            说明：
                - "/" 或 "/index.html"：每次请求都重新读取 html_path 并返回，
                  这样 reclassify.py 重新生成 HTML 后，浏览器刷新即可看到最新内容，
                  无需重启本服务。
                - "/health"：健康检查，直接返回 "ok"。
                - "/open?src=<相对路径>"：只读打开源目录下的某个文件/文件夹。
                  先把 src 参数拼接到 src_root 并取真实路径（realpath，解析软链接/..），
                  然后用 os.path.commonpath 校验解析后的路径必须仍在 src_root 内部，
                  防止通过 "../" 等方式越权访问源目录之外的文件（路径穿越攻击）；
                  校验通过且路径存在时，调用 open_readonly 打开并返回 204。
                - 其他路径：一律返回 404。
            """
            u = urllib.parse.urlparse(self.path)
            if u.path in ("/", "/index.html"):
                try:
                    self._send(200, open(html_path, "rb").read(), "text/html; charset=utf-8")
                except OSError as e:
                    self._send(500, f"cannot read HTML: {e}")
            elif u.path == "/health":
                self._send(200, "ok")
            elif u.path == "/open":
                rel = urllib.parse.parse_qs(u.query).get("src", [""])[0]
                if not rel:
                    return self._send(400, "missing src")
                target = os.path.realpath(os.path.join(src_root, rel.replace("\\", "/")))
                # 安全校验：解析后的真实路径必须仍位于源目录根之内，禁止跳出源目录访问其他文件
                if os.path.commonpath([target, src_real]) != src_real:
                    return self._send(403, "path outside source root")
                if not os.path.exists(target):
                    return self._send(404, f"not found: {target}")
                try:
                    open_readonly(target); self._send(204)
                except Exception as e:                       # noqa: BLE001
                    self._send(500, f"{type(e).__name__}: {e}")
            else:
                self._send(404, "not found")

        def do_POST(self):
            """处理 POST 请求：仅支持 "/reclassify-queue"，用于接收页面提交的待重分类队列。

            说明：
                页面上勾选“需要重新分类”并点击“提交待重分类”后，会把这些单元的列表
                以 JSON 数组形式 POST 到这里。本方法读取请求体、校验其确实是一个
                JSON 数组，然后原样写入 queue_path 文件（覆盖式写入），供
                reclassify.py 后续读取消费。写入成功后返回包含数量和文件名的 JSON。
            """
            u = urllib.parse.urlparse(self.path)
            if u.path != "/reclassify-queue":
                return self._send(404, "not found")
            n = int(self.headers.get("Content-Length", 0))
            try:
                items = json.loads(self.rfile.read(n) or b"[]")
                assert isinstance(items, list)
            except Exception:                                # noqa: BLE001
                return self._send(400, "expected a JSON array")
            json.dump(items, open(queue_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
            self._send(200, json.dumps({"count": len(items), "queue": os.path.basename(queue_path)}),
                       "application/json; charset=utf-8")

    return H

def main():
    """入口函数：加载 HTML 的 meta 信息，启动本地 HTTP 服务并自动打开浏览器。

    说明：
        - 命令行参数（可选）：HTML 路径、端口号；缺省时使用脚本常量 HTML/PORT。
        - 从 HTML 的 __META__ 中读取 srcRoot（源目录根）和 name（数据集名称）；
          若 srcRoot 不是一个存在的目录，只打印警告（/open 功能会因此 404，
          但页面本身仍可正常查看/筛选/导出）。
        - 队列文件路径固定为 "<name>_reclassify_queue.json"，与 HTML 文件同目录。
        - 服务只绑定 127.0.0.1（本机回环地址），不对外网暴露。
        - 启动后延迟 0.5 秒自动用默认浏览器打开页面，随后阻塞运行直到 Ctrl+C。
    """
    a = sys.argv[1:]
    html_path = a[0] if len(a) >= 1 else HTML
    port = int(a[1]) if len(a) >= 2 else PORT
    if not os.path.isfile(html_path):
        sys.exit(f"HTML not found: {html_path!r} — build it with build_review_html.py first.")
    meta = load_meta(html_path)
    src_root = meta.get("srcRoot", "")
    name = meta.get("name", "plan")
    if not src_root or not os.path.isdir(src_root):
        print(f"WARNING: srcRoot from HTML is not a directory ({src_root!r}); /open will 404.")
    queue_path = os.path.join(os.path.dirname(os.path.abspath(html_path)),
                              f"{name}_reclassify_queue.json")
    handler = make_handler(os.path.abspath(html_path), src_root, queue_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"serving {os.path.basename(html_path)}  at {url}")
    print(f"  source root : {src_root}")
    print(f"  reclassify queue -> {queue_path}")
    print("  Ctrl+C to stop.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")

if __name__ == "__main__":
    main()
