# -*- coding: utf-8 -*-
"""Build the single-file HTML review tool from a units.json + target tree.

Edit the constants below and run (Git Bash mangles CJK CLI args, so prefer in-file
constants). ASCII-only paths may instead be passed as argv: UNITS SRC DST OUT [NAME] [BIG].

SRC/DST are shown in the exported plan header; NAME labels the export filenames and
namespaces the browser localStorage progress (so two review pages don't collide).
Leave NAME blank to derive it from the SRC folder name. BIG is the "large package"
file-count threshold used by the review UI's filter/highlight (default 500).

COPY_BACKEND (default True) also copies scripts/review_server.py next to OUT on every
build, so the workspace folder is self-contained (HTML + units.json + plan + backend,
no need to dig into the skill's own scripts/ dir to find the server).

    PYTHONIOENCODING=utf-8 python build_review_html.py
"""
import sys, os, json, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import units_lib as U

# ===== EDIT-ME (or pass argv: UNITS SRC DST OUT [NAME] [BIG]) ==================
UNITS = "./units.json"          # units.json produced by the classify driver
SRC   = "./source"              # source root (shown in the export header)
DST   = "./target-tree"         # existing taxonomy tree (its leaves = valid targets)
OUT   = "./review.html"
NAME  = ""                      # export/label name; blank => basename of SRC
BIG   = 500                     # "large package" threshold (files) for filter/highlight
COPY_BACKEND = True              # also copy review_server.py next to OUT (self-contained workspace)

def copy_backend(out):
    """把 scripts/review_server.py 复制到 out（审阅 HTML）所在的工作空间目录下。

    说明：
        review_server.py 本身不依赖 units_lib（只用标准库），所以可以单独拷贝、
        独立运行。目的是让工作空间目录（HTML + units.json + 计划文件所在的地方）
        自成一体——用户在那个目录里就能直接 `python review_server.py review.html`
        启动后端，不需要再回到 skill 自身的 scripts/ 目录去找这个文件。
        源文件与目标文件路径解析后相同时（out 恰好就在 scripts/ 目录下）跳过，
        避免 shutil.copy2 对同一个文件报错。每次构建都会覆盖复制一份，
        保持工作空间里的副本和 skill 当前版本一致。

    参数：
        out (str): 生成的审阅 HTML 文件路径，决定复制的目标目录。
    返回：
        str | None: 实际复制到的路径；因源和目标相同而跳过时返回 None。
    """
    server_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review_server.py")
    server_dst = os.path.join(os.path.dirname(os.path.abspath(out)), "review_server.py")
    if os.path.abspath(server_src) == os.path.abspath(server_dst):
        return None
    shutil.copy2(server_src, server_dst)
    return server_dst

def main():
    """入口函数：读取 units.json + 目标树叶子列表，把它们注入 HTML 模板，生成审阅页面。

    说明：
        - 参数解析：优先使用 5~6 个 ASCII 命令行参数（units src dst out [name] [big]），
          否则回退使用脚本顶部 EDIT-ME 区域的常量（CJK 路径应写在这里）。
        - name 留空时，自动取 src 目录名作为导出文件名前缀 / localStorage 命名空间。
        - 核心步骤：
            1. 读取 units.json（分类结果行数据）；
            2. 用 units_lib.leaf_dirs(dst) 得到目标树里所有合法的叶子目录；
            3. 组装 meta 信息（name/srcRoot/dstRoot/big，big 为“大包”文件数阈值）；
            4. 读取 templates/review.html 模板，把 __LEAVES__ / __UNITS__ / __META__
               三个占位符替换为对应的 JSON 数据，得到一个独立、无外部依赖的单文件 HTML；
            5. 写出到 out 指定路径；
            6. 若 COPY_BACKEND 为真，把 review_server.py 复制到 out 所在目录
               （见 copy_backend），让工作空间自成一体；
            7. 打印统计信息。
    """
    a = sys.argv[1:]
    units_path, src, dst, out = (a[0], a[1], a[2], a[3]) if len(a) >= 4 else (UNITS, SRC, DST, OUT)
    name = (a[4] if len(a) >= 5 else NAME) or os.path.basename(os.path.normpath(src)) or "plan"
    big = int(a[5]) if len(a) >= 6 else BIG
    units = json.load(open(units_path, encoding="utf-8"))
    leaves = U.leaf_dirs(dst)
    meta = {"name": name, "srcRoot": src, "dstRoot": dst, "big": big}
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                            "templates", "review.html"), encoding="utf-8").read()
    html = (tpl.replace("__LEAVES__", json.dumps(leaves, ensure_ascii=False))
               .replace("__UNITS__", json.dumps(units, ensure_ascii=False))
               .replace("__META__", json.dumps(meta, ensure_ascii=False)))
    open(out, "w", encoding="utf-8").write(html)
    backend_path = copy_backend(out) if COPY_BACKEND else None
    print(f"name: {name}  big>{big}  leaves: {len(leaves)}  units: {len(units)}  bytes: {len(html)}\nwritten: {out}"
          + (f"\nbackend copied: {backend_path}" if backend_path else ""))

if __name__ == "__main__":
    main()
