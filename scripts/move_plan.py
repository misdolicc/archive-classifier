# -*- coding: utf-8 -*-
"""Execute a human-reviewed move plan — COPY (default) or MOVE each unit into its leaf.

Reads the reviewed plan exported from the HTML review tool (`…_已审阅.txt`) — or the
original `…_文件分类移动计划.txt` — and, for every `源单元  =>  目标叶子` line, places the
whole source unit (a package folder OR a loose file) INTO the target leaf directory.

  * Whole-unit granularity — dump packages are never exploded file-by-file.
  * Conflict-safe — an existing destination gets a ` (2)`, ` (3)` … suffix; nothing is
    overwritten or merged.
  * Targets are validated against the REAL leaves of DST (sep/case-insensitive); an
    unknown leaf is skipped (or created, if CREATE_MISSING_LEAVES).
  * DRY_RUN first — prints every resolved action and writes a log, but changes nothing.
    Review it, then set DRY_RUN=False to actually run.

Git Bash mangles CJK CLI args, so keep the CJK paths in the constants below and run the
file (an ASCII plan path may instead be passed as argv[1]):

    PYTHONIOENCODING=utf-8 python move_plan.py
"""
import sys, os, re, shutil, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import units_lib as U

# ===== EDIT-ME ================================================================
PLAN      = "./plan_已审阅.txt"   # the reviewed plan exported from the HTML tool
SRC_ROOT  = ""                    # source root; blank => read from the plan header
DST_ROOT  = ""                    # target root; blank => read from the plan header
MODE      = "copy"                # "copy" (keep source) or "move"
DRY_RUN   = True                  # True = preview only; set False to actually apply
CREATE_MISSING_LEAVES = False     # create a target leaf dir if it isn't in the tree yet
LOG       = ""                    # blank => alongside PLAN as <plan>_move_log.txt

# ===== plan parsing ===========================================================
# `源单元  =>  目标叶子   （N 文件）[待确认：…]`  — leaf may contain spaces; anchored on 文件）.
UNIT = re.compile(r'^(.*?)\s+=>\s+(.*?)\s+（\s*[\d,]+\s*文件）')

def parse_roots(text):
    """从计划文本的文件头中解析出“源目录根”和“目标目录根”。

    说明：
        计划文件第一行形如 `源目录根：xxx    目标目录根：yyy`，本函数用正则提取
        两个路径并去除首尾空白及末尾的路径分隔符。若未匹配到（例如计划文件被
        手动改动过格式），返回两个空字符串，调用方需回退到脚本常量 SRC_ROOT/DST_ROOT。

    参数：
        text (str): 计划文件的完整文本内容。
    返回：
        tuple(str, str): (源目录根路径, 目标目录根路径)；解析失败时均为 ""。
    """
    m = re.search(r'源目录根：\s*(.+?)\s+目标(?:目录)?根：\s*(.+?)(?:\s{2,}|\s*（|$)', text)
    if not m:
        return "", ""
    return m.group(1).strip().rstrip("/\\"), m.group(2).strip().rstrip("/\\")

def parse_units(lines):
    """从计划文本的每一行中解析出 (源单元, 目标叶子, 是否待确认) 三元组列表。

    说明：
        使用模块级正则 UNIT 匹配 `源单元  =>  目标叶子   （N 文件）` 格式的行
        （目标叶子路径本身可以包含空格，正则以 "（数字 文件）" 为锚点结束匹配）。
        若该行还带有 `[待确认：...]` 标记，则第三个元素为 True，提示该单元
        在最初分类时被标记为不确定，执行时会在日志中额外打印 [待确认] 提示。
        不匹配 UNIT 正则的行（如注释行、空行、文件头）会被直接忽略。

    参数：
        lines (list[str]): 计划文件按行拆分后的列表。
    返回：
        list[tuple[str, str, bool]]: [(源单元路径, 目标叶子路径, 是否待确认), ...]。
    """
    units = []
    for ln in lines:
        m = UNIT.match(ln.strip())
        if m:
            units.append((m.group(1).strip(), m.group(2).strip(), "待确认" in ln))
    return units

# ===== fs helpers =============================================================
def unique_dest(dest, is_dir):
    """生成一个尚不存在的目标路径——若 dest 已存在，则依次尝试追加 ` (2)`、` (3)` … 后缀。

    说明：
        这是“冲突安全”（conflict-safe）的核心实现：绝不覆盖或合并已存在的目标，
        而是给新内容一个不冲突的新名字。对目录，后缀直接加在目录名后；对文件，
        后缀插在文件名主干和扩展名之间（保持扩展名不变，如 `a.txt` -> `a (2).txt`）。

    参数：
        dest (str): 期望的目标路径（尚未确定是否可用）。
        is_dir (bool): dest 对应的源是否为目录（决定是否拆分扩展名）。
    返回：
        str: 一个当前文件系统上不存在的可用路径。
    """
    if not os.path.exists(dest):
        return dest
    parent, name = os.path.split(dest)
    stem, ext = (name, "") if is_dir else os.path.splitext(name)
    i = 2
    while True:
        cand = os.path.join(parent, f"{stem} ({i}){ext}")
        if not os.path.exists(cand):
            return cand
        i += 1

def main():
    """入口函数：解析计划文件，逐个单元执行复制/移动（或在 DRY_RUN 模式下只打印预览）。

    说明（主要流程）：
        1. 确定计划文件路径（命令行参数或脚本常量 PLAN），读取其内容。
        2. 解析源目录根/目标目录根：优先用脚本常量 SRC_ROOT/DST_ROOT，为空时
           从计划文件头解析（parse_roots）；两者都拿不到则报错退出。
        3. 校验 SRC_ROOT/DST_ROOT 必须是已存在的目录，MODE 必须是 "copy" 或 "move"。
        4. 用 parse_units 解析出所有 `源单元 => 目标叶子` 行。
        5. 构建目标树真实叶子目录的小写/统一分隔符 -> 原始大小写 的映射表 leafmap，
           用于把计划里写的目标路径（可能大小写或分隔符不同）匹配回真实叶子目录。
        6. 对每个单元：
             - 校验目标叶子是否存在于 leafmap；不存在时，按 CREATE_MISSING_LEAVES
               决定是新建该叶子目录，还是跳过（SKIP）并计入 skipped 计数；
             - 校验源路径是否存在；不存在则记录 ERROR 并计入 errors 计数；
             - 计算冲突安全的目标路径（unique_dest），记录该单元的操作日志；
             - 若非 DRY_RUN，则实际执行 copytree/copy2（copy 模式）或 shutil.move
               （move 模式），异常会被捕获并计入 errors。
        7. 汇总统计（计划数/跳过数/出错数），把完整日志写入 LOG 文件，
           并根据是否有错误决定进程退出码。
    """
    plan_path = sys.argv[1] if len(sys.argv) > 1 else PLAN
    if not os.path.isfile(plan_path):
        sys.exit(f"plan not found: {plan_path!r}")
    raw = open(plan_path, encoding="utf-8-sig").read()

    hsrc, hdst = parse_roots(raw)
    src_root = (SRC_ROOT or hsrc).rstrip("/\\")
    dst_root = (DST_ROOT or hdst).rstrip("/\\")
    if not src_root or not dst_root:
        sys.exit("Cannot determine SRC_ROOT/DST_ROOT — set them in the script, or ensure the "
                 "plan header contains 源目录根 / 目标根.")
    if not os.path.isdir(src_root): sys.exit(f"SRC_ROOT is not a directory: {src_root!r}")
    if not os.path.isdir(dst_root): sys.exit(f"DST_ROOT is not a directory: {dst_root!r}")
    if MODE not in ("copy", "move"): sys.exit("MODE must be 'copy' or 'move'")

    units = parse_units(raw.splitlines())
    if not units:
        sys.exit("No `源单元 => 目标叶子` lines parsed — is this a reviewed plan .txt?")

    # 目标树中真实叶子目录的映射：key 为“分隔符统一为 /、去除首尾 /、转小写”后的字符串，
    # value 为磁盘上真实的大小写形式，用于把计划里的目标路径匹配回真实目录。
    # 用可信清单（stable_leaf_dirs）而不是实时扫描 dst_root——避免目标树里已经存在的、
    # 之前分类挪进去的内容（比如一个没有子目录的产品文件夹）被误判成一个新叶子。
    leafmap = {l.replace("\\", "/").strip("/").lower(): l for l in U.stable_leaf_dirs(dst_root)}

    log, out = [], print
    def rec(s):
        """记录一行日志：既追加到内存日志列表 log（最终写入日志文件），也立刻打印到控制台。"""
        log.append(s); out(s)

    tag = "DRY-RUN (no changes)" if DRY_RUN else MODE.upper()
    rec(f"# move plan · {tag} · {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    rec(f"# SRC_ROOT = {src_root}")
    rec(f"# DST_ROOT = {dst_root}")
    rec(f"# units = {len(units)}   mode = {MODE}   create_missing_leaves = {CREATE_MISSING_LEAVES}")
    rec("")

    ok = skipped = errors = 0
    for src_rel, leaf_rel, unc in units:
        s_posix = src_rel.replace("\\", "/").strip("/")
        abs_src = os.path.join(src_root, *s_posix.split("/"))
        key = leaf_rel.replace("\\", "/").strip("/").lower()
        note = "  [待确认]" if unc else ""

        actual = leafmap.get(key)
        if actual is None:
            leaf_dir = os.path.join(dst_root, *leaf_rel.replace("\\", "/").strip("/").split("/"))
            if CREATE_MISSING_LEAVES:
                rec(f"MKLEAF  {leaf_dir}")
                if not DRY_RUN:
                    os.makedirs(leaf_dir, exist_ok=True)
                    # 这是刚刚真的新建的分类叶子（不是被移动进去的内容），登记进可信清单，
                    # 这样以后的分类才会把它当成一个合法目标，而不是要等下次实时扫描才发现。
                    U.add_leaves(dst_root, leaf_rel.replace("\\", "/").strip("/"))
            else:
                rec(f"SKIP    invalid leaf (not in target tree): {leaf_rel}  <=  {src_rel}{note}")
                skipped += 1
                continue
        else:
            leaf_dir = os.path.join(dst_root, *actual.split("/"))

        if not os.path.exists(abs_src):
            rec(f"ERROR   source missing: {abs_src}")
            errors += 1
            continue

        is_dir = os.path.isdir(abs_src)
        dest = unique_dest(os.path.join(leaf_dir, os.path.basename(abs_src)), is_dir)
        renamed = "  [renamed: conflict]" if os.path.basename(dest) != os.path.basename(abs_src) else ""
        verb = ("COPY" if MODE == "copy" else "MOVE") + ("(dir)" if is_dir else "")
        rec(f"{verb}  {abs_src}  ->  {dest}{renamed}{note}")

        if DRY_RUN:
            ok += 1
            continue
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if MODE == "copy":
                shutil.copytree(abs_src, dest) if is_dir else shutil.copy2(abs_src, dest)
            else:
                shutil.move(abs_src, dest)
            ok += 1
        except Exception as e:
            rec(f"ERROR   {type(e).__name__}: {e}")
            errors += 1

    rec("")
    rec(f"# summary: {'planned' if DRY_RUN else 'done'}={ok}  skipped={skipped}  errors={errors}")
    log_path = LOG or (os.path.splitext(plan_path)[0] + "_move_log.txt")
    open(log_path, "w", encoding="utf-8").write("\n".join(log) + "\n")
    out(f"\nlog written: {log_path}")
    if DRY_RUN:
        out("DRY_RUN=True — nothing was changed. Set DRY_RUN=False in the script to apply.")
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
