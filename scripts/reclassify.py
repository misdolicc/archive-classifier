# -*- coding: utf-8 -*-
"""Re-classify the units a human flagged "需要重新分类", then merge back into the review HTML.

Round-trip (feature 2):
  1. In the review page, tick "需要重新分类" on the wrong rows -> 提交待重分类
     (backend writes <name>_reclassify_queue.json; or file-mode downloads the same JSON).
  2. Improve the rules in your driver `run.py` (same classify() method as before) if needed.
  3. Run this tool: it re-runs classify() on ONLY the queued units, updates units.json (new
     leaf/status/note + a bumped `rev`), and rebuilds the HTML.
  4. Refresh the page. The bumped `rev` makes the page drop stale local state for those units,
     so they show the fresh target and re-enter review (unchecked, unreviewed).

`classify()` is imported from your driver so the classification logic stays identical to the
first pass. For one-off manual placements, add entries to OVERRIDES (src -> leaf).

    PYTHONIOENCODING=utf-8 python reclassify.py
"""
import sys, os, re, json, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import units_lib as U
import build_review_html as B

# ===== EDIT-ME ================================================================
DRIVER = "./run.py"        # your classify driver (defines classify(rel)); == the first-pass logic
UNITS  = "./units.json"    # the plan units.json to update in place
DST    = "./target-tree"   # target tree (leaf validity check + HTML rebuild)
HTML   = "./review.html"   # the review page to rebuild
QUEUE  = ""                # blank => <name>_reclassify_queue.json next to HTML (from the backend)
OVERRIDES = {}             # optional manual placements, e.g. {"02_行业装备/华为": "01_物料手册/华为/Datasheet"}

_key = lambda s: s.replace("\\", "/").strip("/")

def load_driver(path):
    """动态加载分类驱动脚本（如 run.py），返回其模块对象，用于复用其中的 classify() 函数。

    说明：
        使用 importlib 按文件路径动态导入模块（而非普通 import），这样重分类时
        用的正是第一遍分类时同一个 run.py 里的 classify 逻辑（改进规则后也是
        同一份代码，保证前后两次分类方法一致）。若目标文件没有定义 classify 函数，
        直接报错退出。

    参数：
        path (str): 驱动脚本文件路径（DRIVER 常量）。
    返回：
        module: 加载后的模块对象（调用方通常只用它的 .classify 属性）。
    """
    spec = importlib.util.spec_from_file_location("driver", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    if not hasattr(m, "classify"):
        sys.exit(f"{path} has no classify(rel) function.")
    return m

def read_meta(html_path):
    """从审阅 HTML 中提取内嵌的 __META__ JSON（与 review_server.py 的 load_meta 作用相同）。

    参数：
        html_path (str): 审阅 HTML 文件路径。
    返回：
        dict: 解析出的 meta 信息（name/srcRoot/dstRoot/big），找不到时为空字典。
    """
    m = re.search(r'id="metaData">(.*?)</script>', open(html_path, encoding="utf-8").read(), re.S)
    return json.loads(m.group(1)) if m else {}

def main():
    """入口函数：对“待重分类队列”中的单元重新分类，合并回 units.json 并重建审阅页面。

    说明（对应 SKILL 中描述的往返流程 round-trip）：
        1. 校验 HTML 和 units.json 都存在；从 HTML 读取 meta 得到队列文件的默认路径
           "<name>_reclassify_queue.json"（除非 QUEUE 常量另外指定）。
        2. 队列文件不存在则报错退出——需要先在审阅页面勾选“需要重新分类”并提交。
        3. 读取队列中的单元 src 集合 queued，以及 OVERRIDES 中手动指定的覆盖项 ovr。
        4. 用 load_driver 加载 DRIVER（即 run.py）里的 classify 函数——与首次分类
           使用完全相同的方法，保证规则一致性。
        5. 遍历 units.json 中的每一行：只处理 src 落在 queued 集合中的行；
           若该 src 在 OVERRIDES 中，直接使用人工指定的 leaf（status 固定为
           "normal"，note 为 "手动指定"）；否则重新调用 classify(r["src"])。
           更新该行的 leaf/status/note，并把 rev（版本号）加 1——rev 提升是关键：
           页面据此判断该单元的本地审阅状态（已勾选/已复核等）已过期，会在下次
           刷新时重置为未审阅，从而让用户看到新的分类结果并重新确认。
           同时统计 changed（目标是否真的变化了）和 invalid（新 leaf 是否仍不是
           合法叶子目录）两个计数，并打印每一行的处理结果。
        6. 把更新后的 rows 整体写回 UNITS（units.json）。
        7. 复用 build_review_html.main()（通过临时替换 sys.argv 传参）重建 HTML，
           保持原有的 srcRoot/name/big 不变，只刷新 units 数据。
        8. 把已消费的队列文件重命名为 "<queue>.done"，防止之后被重复应用。
        9. 打印汇总信息，若存在 invalid（非法叶子）则以退出码 1 提示需要关注。
    """
    if not os.path.isfile(HTML):  sys.exit(f"HTML not found: {HTML!r} (build it first).")
    if not os.path.isfile(UNITS): sys.exit(f"units.json not found: {UNITS!r}")
    meta = read_meta(HTML)
    queue_path = QUEUE or os.path.join(os.path.dirname(os.path.abspath(HTML)),
                                       f"{meta.get('name','plan')}_reclassify_queue.json")
    if not os.path.isfile(queue_path):
        sys.exit(f"queue not found: {queue_path!r} — submit '需要重新分类' from the page first.")

    queued = {_key(it["src"]) for it in json.load(open(queue_path, encoding="utf-8"))}
    ovr = {_key(k): v for k, v in OVERRIDES.items()}
    classify = load_driver(DRIVER).classify
    rows = json.load(open(UNITS, encoding="utf-8"))
    leaves = {l.replace("\\", "/").lower() for l in U.leaf_dirs(DST)}

    changed = invalid = 0
    print(f"# reclassify {len(queued)} queued unit(s) from {os.path.basename(queue_path)}\n")
    for r in rows:
        k = _key(r["src"])
        if k not in queued:
            continue
        old = r.get("leaf", "")
        if k in ovr:
            leaf, status, note = ovr[k], "normal", "手动指定"
        else:
            leaf, status, note = classify(r["src"])       # same method as the first pass
        r["leaf"], r["status"] = leaf, status
        r["note"] = (note + " · " if note else "") + "已重新分类"
        r["rev"] = int(r.get("rev", 0)) + 1
        moved = old != leaf
        changed += moved
        bad = leaf.replace("\\", "/").lower() not in leaves
        invalid += bad
        print(f"  {'MOVED ' if moved else 'same  '}{r['src']}\n      {old}  ->  {leaf}"
              + ("   [!! not a real leaf]" if bad else ""))

    json.dump(rows, open(UNITS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    # rebuild the HTML preserving the dataset's srcRoot / name / big
    sys.argv = ["build_review_html.py", UNITS, meta.get("srcRoot", ""), DST, HTML,
                meta.get("name", "plan"), str(int(meta.get("big", 500) or 500))]
    B.main()

    # queue consumed -> archive so a stale queue isn't re-applied
    try: os.replace(queue_path, queue_path + ".done")
    except OSError: pass
    print(f"\n# done: {len(queued)} reclassified, {changed} changed target, {invalid} invalid leaf."
          f"\n# refresh the page to review them (they reset to unchecked/unreviewed).")
    sys.exit(1 if invalid else 0)

if __name__ == "__main__":
    main()
