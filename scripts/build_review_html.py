# -*- coding: utf-8 -*-
"""Build the single-file HTML review tool from a units.json + target tree.

Edit the constants below and run (Git Bash mangles CJK CLI args, so prefer in-file
constants). ASCII-only paths may instead be passed as argv: UNITS SRC DST OUT [NAME] [BIG].

SRC/DST are shown in the exported plan header; NAME labels the export filenames and
namespaces the browser localStorage progress (so two review pages don't collide).
Leave NAME blank to derive it from the SRC folder name. BIG is the "large package"
file-count threshold used by the review UI's filter/highlight (default 500).

    PYTHONIOENCODING=utf-8 python build_review_html.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import units_lib as U

# ===== EDIT-ME (or pass argv: UNITS SRC DST OUT [NAME] [BIG]) ==================
UNITS = "./units.json"          # units.json produced by the classify driver
SRC   = "./source"              # source root (shown in the export header)
DST   = "./target-tree"         # existing taxonomy tree (its leaves = valid targets)
OUT   = "./review.html"
NAME  = ""                      # export/label name; blank => basename of SRC
BIG   = 500                     # "large package" threshold (files) for filter/highlight

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
            5. 写出到 out 指定路径，并打印统计信息。
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
    print(f"name: {name}  big>{big}  leaves: {len(leaves)}  units: {len(units)}  bytes: {len(html)}\nwritten: {out}")

if __name__ == "__main__":
    main()
