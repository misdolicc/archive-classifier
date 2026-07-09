# -*- coding: utf-8 -*-
"""Driver template: copy this, edit the 3 marked sections, run it.

    PYTHONIOENCODING=utf-8 python run.py

IMPORTANT (Windows): Git Bash mangles CJK characters passed as command-line args or
here-docs. So DON'T pass 中文 paths on the CLI — put them in the EDIT-ME constants below
and run this as a UTF-8 file. Everything generic lives in units_lib.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import units_lib as U

# ===== EDIT 1/3 — paths (absolute; forward slashes, valid on Windows too) ======
SRC   = "./source"          # the messy source folder to classify
DST   = "./target-tree"     # the existing taxonomy tree (its leaves = valid targets)
PLAN  = "./move-plan.txt"
JSONF = "./units.json"

# Catch-all leaf for units no rule matched — MUST be a real leaf in DST (e.g. a
# category's "其他"/"Other"/"待归档" folder). Leave blank to be forced to set it.
FALLBACK_LEAF = ""          # e.g. "05_学习资料/其他"

# ===== EDIT 2/3 — unit depth per top-level source folder (top entry = depth 1) =
# Vendor/product/topic/competitor folders are usually depth 3; a flat category depth 2.
# Descend deeper (e.g. per component-type or per standard-body) where useful.
BASE = {}   # e.g. {"01_物料手册": 3, "02_行业装备": 3, "05_学习资料": 2}
def eff_depth(parts):
    """返回给定路径分段（parts）所在分支应使用的“单元深度”。

    说明：
        由 units_lib.enumerate_units 调用，用于判断某个目录该在哪一层被当作
        一个完整的分类单元（而不是继续往下拆分）。parts 是路径按 "/" 分割后的
        列表，parts[0] 即顶层目录名。默认深度为 2（顶层目录 -> 子目录 即为单元），
        可在 BASE 字典里为特定顶层目录指定不同的深度（例如厂商/产品/主题类目录
        通常需要深度 3：顶层 -> 厂商 -> 产品）。也可以按需在函数体内针对更细的
        分支追加特殊规则（见下方注释示例）。

    参数：
        parts (list[str]): 路径按 "/" 分割后的各段名称。
    返回：
        int: 该分支的单元深度。
    """
    top = parts[0]; d = BASE.get(top, 2)
    return d

# ===== EDIT 3/3 — classifier: ordered keyword rules, first match wins ==========
# Leaf paths use posix `/`; matching is sep- and case-insensitive.
def classify(rel):
    """核心分类函数：根据源单元的相对路径 rel，决定它应归入目标树的哪个叶子目录。

    说明：
        - 按“先按顶层类目限定范围，再用关键字细化”的方式编写有序规则，第一条
          匹配的规则生效（first match wins）。
        - OK(leaf)：返回确定的分类结果（status="normal"）。
        - UNC(leaf, why)：返回不确定的分类结果（status="uncertain"），并附上
          原因 why，供人工在审阅页面中重点复核。
        - 所有规则都未命中时，兜底落到 FALLBACK_LEAF（必须是目标树中真实存在的
          一个"其他/待归档"类叶子目录），并标记为 uncertain，以便该单元能在
          审阅阶段被发现并人工处理。

    参数：
        rel (str): 源单元相对于源根目录的 posix 路径。
    返回：
        tuple(str, str, str): (目标叶子路径 leaf, 状态 status, 备注 note)。
    """
    parts = rel.split("/"); top = parts[0]; low = rel.lower()
    OK  = lambda leaf: (leaf, "normal", "")
    UNC = lambda leaf, why="待人工复核": (leaf, "uncertain", why)
    # Scope by top-level category, then keyword-refine. Fall back to FALLBACK_LEAF
    # with UNC(...) so fuzzy items surface for review.
    # if top == "02_行业装备":
    #     return OK("同行业装备资料/半导体检测装备" if "半导体" in rel
    #               else "同行业装备资料/汽车电子检测装备")
    return UNC(FALLBACK_LEAF, "未归类 — 待人工复核")

# ===== run：主流程 — 枚举单元 -> 分类 -> 写出 units.json/计划文件 -> 打印验收结果 =====
if __name__ == "__main__":
    if not os.path.isdir(SRC) or not os.path.isdir(DST):
        sys.exit(f"EDIT-ME: SRC/DST must be existing dirs.  SRC={SRC!r}  DST={DST!r}")
    if not FALLBACK_LEAF:
        sys.exit("EDIT-ME: set FALLBACK_LEAF to a real catch-all leaf in DST (e.g. '.../其他').")
    units = U.enumerate_units(SRC, eff_depth)
    rows = U.build_rows(units, classify)
    U.dump_json(rows, JSONF)
    U.write_plan(rows, PLAN, SRC + "/", DST + "/")
    r = U.verify(rows, SRC, DST)
    print("units:", len(rows), "| files:", r["covered_files"], "/", r["total_files"],
          "| coverage_ok:", r["coverage_ok"], "| uncertain:", r["uncertain"],
          "| invalid_leaves:", len(r["invalid_leaves"]), "| dups:", len(r["duplicate_units"]))
    for b in r["invalid_leaves"]:
        print("  INVALID LEAF ->", b)
