# -*- coding: utf-8 -*-
"""Reusable helpers for archive-classifier.

Generic, project-independent parts of building a leaf-only, package-aware move plan:
  walk / leaf discovery / unit enumeration / file counting / plan writing / verification.

The caller supplies two project-specific callables:
  eff_depth(parts) -> int   # unit depth for a path (see enumerate_units)
  classify(rel)    -> (leaf, status, note)   # 'normal' | 'uncertain'

说明：本模块是 archive-classifier 的通用工具库，包含以下通用逻辑：
    目录遍历（walk）、叶子目录发现（leaf_dirs）、单元枚举（enumerate_units，保证
    整包/整文件夹不被拆散）、文件计数（summarize）、计划文件写出（write_plan/dump_json）、
    以及结果验收（verify）。调用方（各项目的分类驱动脚本 run.py）只需提供两个
    与项目相关的函数：eff_depth(parts) 决定某路径的单元深度，classify(rel) 决定
    某个源单元应归入哪个目标叶子目录。
"""
import os, json
from collections import defaultdict, Counter


def walk(src):
    """遍历 src 目录，返回该目录下所有子目录与文件的 posix 相对路径。

    说明：
        - 使用 os.walk 递归遍历 src 下的所有内容。
        - dirs：所有子目录的相对路径集合（set），路径分隔符统一转换为 posix 风格 "/"。
        - files：所有文件的相对路径列表（list），同样使用 "/" 分隔。
        - 顶层目录本身（相对路径为 "."）不计入 dirs，但其下的文件会被计入 files（不带前缀）。

    参数：
        src (str): 要遍历的根目录路径。
    返回：
        tuple(set[str], list[str]): (子目录相对路径集合, 文件相对路径列表)。
    """
    dirs, files = set(), []
    for dp, dn, fn in os.walk(src):
        rel = os.path.relpath(dp, src).replace("\\", "/")
        if rel != ".":
            dirs.add(rel)
        for f in fn:
            files.append((rel + "/" + f) if rel != "." else f)
    return dirs, files


def leaf_dirs(dst):
    """找出 dst（目标分类树）下所有的“叶子目录”（没有子目录的目录），即唯一合法的归档目标。

    说明：
        - 叶子目录 = 该目录下不再包含任何子目录（dn 为空列表）。
        - 只有叶子目录才是文件/单元可以放入的合法目标位置，中间节点不允许直接放文件。
        - 返回结果统一使用 posix 分隔符 "/"，并按字母序排序、去重。
        - posix 的 "/" 在 Windows 上同样合法，作为全局唯一的规范分隔符使用；
          审阅页面（review UI）在匹配时会自动归一化用户粘贴内容中的 "\\" 和大小写差异。

    参数：
        dst (str): 目标分类树的根目录路径。
    返回：
        list[str]: 所有叶子目录的相对路径（posix 风格），已排序去重。
    """
    out = []
    for dp, dn, fn in os.walk(dst):
        if not dn:
            rel = os.path.relpath(dp, dst)
            if rel != ".":
                out.append(rel.replace("\\", "/"))
    return sorted(set(out))


MANIFEST_NAME = ".archive_classifier_leaves.json"


def _manifest_path(dst):
    """返回 dst（目标分类树）对应的“可信叶子清单”文件路径（藏在 dst 根目录下的隐藏文件）。"""
    return os.path.join(dst, MANIFEST_NAME)


def load_leaf_manifest(dst):
    """读取 dst 下持久化保存的"可信叶子清单"（如果存在的话）。

    说明：
        清单是一份 JSON 文件（`dst/.archive_classifier_leaves.json`），内容就是一份
        posix 相对路径的列表，代表"这些才是目标树本来的分类叶子"。它的存在是为了
        解决一个问题：一旦有内容被移动进目标树，`leaf_dirs(dst)` 这种靠实时扫描
        目录结构（"没有子目录 = 叶子"）来判断叶子的方式就会被污染——被移进去的
        文件夹自己如果没有子目录，会被误判成新叶子；而它所在的原叶子目录因为
        多了这个子目录，反而不再被判定为叶子了。清单一旦生成，就不再依赖实时
        扫描，而是把"目标树本来的分类骨架长什么样"固定下来，跨多次分类、
        跨工作空间、跨机器都能找到同一份清单，避免上述污染反复重现。

    参数：
        dst (str): 目标分类树的根目录路径。
    返回：
        list[str] | None: 清单存在时返回其内容（排序去重后的叶子路径列表）；
            清单文件不存在时返回 None（调用方应据此触发一次性的初始化/引导）。
    """
    p = _manifest_path(dst)
    if not os.path.isfile(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def save_leaf_manifest(dst, leaves):
    """把叶子列表 leaves 写入 dst 下的可信叶子清单文件（排序去重后保存）。

    参数：
        dst (str): 目标分类树的根目录路径。
        leaves (list[str]): 要保存的叶子相对路径列表（posix 风格）。
    返回：
        list[str]: 实际写入的内容（排序去重后）。
    """
    leaves = sorted(set(l.replace("\\", "/").strip("/") for l in leaves))
    json.dump(leaves, open(_manifest_path(dst), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return leaves


def stable_leaf_dirs(dst):
    """获取"可信的"目标树叶子列表——优先用持久化清单，而不是每次都实时扫描 dst。

    说明：
        这是驱动脚本（run.py/verify_coverage.py/build_review_html.py/move_plan.py/
        reclassify.py）应该调用的入口，取代直接调用 `leaf_dirs(dst)`：
        - 若 dst 下已经有可信叶子清单（`load_leaf_manifest` 不为 None），直接返回它，
          **不会**再去实时扫描 dst——这样即使目标树里已经混入了之前分类挪进去的
          内容（文件夹），也不会被误判成新叶子，原来的叶子也不会因为多了子目录
          而被误判成非叶子。
        - 若 dst 下还没有清单（第一次在这棵目标树上跑分类），退化为实时扫描
          `leaf_dirs(dst)`，并把结果保存成清单——之后每次调用都会用这份快照。
          **重要前提**：第一次生成快照时，目标树最好还是"干净"的分类骨架
          （还没有被移动过内容进去），这样快照才准确；如果目标树在用这个工具之前
          就已经手动移动过一些内容进去，第一次生成的清单会把当时的混合状态
          当成基准——如有需要可以打开生成的 JSON 文件手动核对/修正，
          或者删掉清单文件、确认目标树恢复干净后让它重新引导生成。
        - 目标树后续真的新增了分类类目（人工/Agent 新建的叶子目录，而不是被移动
          进去的内容），不会被这份清单自动发现——需要显式调用 `add_leaves()`
          登记，见该函数说明。

    参数：
        dst (str): 目标分类树的根目录路径。
    返回：
        list[str]: 可信的叶子相对路径列表（posix 风格）。
    """
    leaves = load_leaf_manifest(dst)
    if leaves is not None:
        return leaves
    return save_leaf_manifest(dst, leaf_dirs(dst))


def add_leaves(dst, *new_leaves):
    """把明确新增的分类叶子目录登记进可信清单（用于目标树"真的"扩展了分类类目时）。

    说明：
        当源目录里出现了目标树完全没有对应位置的内容、经确认后新建了目标树的
        叶子目录时（工作流"处理目标树里没有的类别"那一步），**必须**紧接着调用
        本函数把新叶子路径登记进清单——否则 `stable_leaf_dirs()` 不会重新扫描
        目标树，永远不会发现这个刚建好的新叶子。
        本函数不会重新扫描整个 dst（不会重新触发实时结构判断），只是把明确
        知道是"新分类类目"的路径追加进已有清单（清单不存在时，先用当前
        `leaf_dirs(dst)` 引导一份，再追加）——这是刻意的：区分"新建的分类目录"
        和"被移动进去的内容目录"这件事，只能靠人工/Agent 明确知道自己做了什么，
        没法靠重新扫描目标树自动分辨（那正是这一整套机制要避免的污染）。

    参数：
        dst (str): 目标分类树的根目录路径。
        *new_leaves (str): 一个或多个新叶子的相对路径（posix 风格）。
    返回：
        list[str]: 更新后的完整叶子列表（已保存）。
    """
    current = load_leaf_manifest(dst)
    if current is None:
        current = leaf_dirs(dst)
    return save_leaf_manifest(dst, list(current) + list(new_leaves))


def summarize(src):
    """对源目录做一次快速摸底：统计每个顶层条目下的文件总数（子目录递归计入）以及总文件数。

    说明：
        - 用于分类前的快速侦察（recon），避免逐文件列出，只按顶层分组统计规模。
        - per_top 按文件数从多到少排序，便于快速看出源目录中“体量集中在哪里”。

    参数：
        src (str): 源目录路径。
    返回：
        dict: {"total": 文件总数, "per_top": {顶层目录名: 文件数, ...}（按数量降序）}。
    """
    dirs, files = walk(src)
    per = Counter()
    for f in files:
        per[f.split("/")[0]] += 1
    return {"total": len(files), "per_top": dict(per.most_common())}


def _depth(rel):
    """计算一个 posix 相对路径的深度（即按 "/" 分割后的段数）。顶层条目深度为 1。"""
    return len(rel.split("/"))


def preview_depth(src, prefix="", max_depth=4, sample=8):
    """按【绝对深度】展示某个（子）目录树的结构样本，供人工/Agent 决定 eff_depth 该怎么配置。

    说明：
        `eff_depth` 现在不该是"拍脑袋给每个顶层文件夹定一个数字"，而应该先看一眼
        该分支下子目录的真实形状——是所有子分支都整齐划一在同一层，还是有的分支
        更深/更浅、需要分开配置。本函数就是为了让这一步"看一眼"变得省事：
        它按深度分层列出 prefix 子树下每一层出现的目录（最多 sample 个样本），
        并标注每个样本目录是否还有子目录（`has_subdir`），据此可以判断"这一层是不是
        已经是一个个完整的包/产品"还是"还得再往下一层才对"。

        深度编号与 `eff_depth`/`enumerate_units` 完全一致：顶层条目深度为 1，
        从 src 根目录数起，与 prefix 无关（prefix 只是用来限定只看某个分支，
        不改变深度编号的起点）。

        典型用法（分类前，决定某个顶层分支该设几层深度时）：
            U.preview_depth(SRC, "华为服务器资料")
            # {2: {"count": 12, "sample": [{"path": "华为服务器资料/交换机CE6857", "has_subdir": False}, ...]},
            #  3: {"count": 40, "sample": [...]}}
        如果发现深度 2 的目录大多 has_subdir=False（已经是完整产品包），
        depth=2 就该是这个分支的单元深度；如果深度 2 的目录几乎都 has_subdir=True
        （说明下面还分了"资料/驱动/固件"等子类别，产品本身在深度 3），就该设 3。
        如果同一个顶层分支下不同子分支的形状不一样，`eff_depth(parts)` 可以按
        `parts[1]`（甚至更深）再细分，不是只能按 `parts[0]` 查一张固定表。

    参数：
        src (str): 源目录路径。
        prefix (str): 只看这个子树下的结构（posix 相对路径，如 "华为服务器资料"）；
            留空则从 src 根目录（深度 1）开始展示整体形状。
        max_depth (int): 最多展示到第几层深度，避免对超深的树输出过多内容。
        sample (int): 每一层最多展示几个样本目录（按字母序取前 N 个）。
    返回：
        dict[int, dict]: {深度: {"count": 该深度目录总数, "sample": [{"path", "has_subdir"}, ...]}}。
    """
    dirs, _ = walk(src)
    base = prefix.replace("\\", "/").strip("/")
    dirset = set(dirs)

    def has_subdir(d):
        pre, dd = d + "/", _depth(d) + 1
        return any(x.startswith(pre) and _depth(x) == dd for x in dirset)

    by_depth = defaultdict(list)
    for d in dirs:
        if base and not (d == base or d.startswith(base + "/")):
            continue
        if base and d == base:
            continue
        dd = _depth(d)
        if dd <= max_depth:
            by_depth[dd].append(d)

    out = {}
    for dd in sorted(by_depth):
        ds = sorted(by_depth[dd])
        out[dd] = {"count": len(ds),
                    "sample": [{"path": d, "has_subdir": has_subdir(d)} for d in ds[:sample]]}
    return out


def enumerate_units(src, eff_depth):
    """枚举“覆盖单元”（coverage units），确保每一个文件都恰好归属于一个单元。

    说明：
        “单元”是分类的最小整体处理粒度——一个软件包、一个产品资料夹、或一个散落文件，
        整体作为一个单元参与分类，不会被拆散到文件级别（除非它本身就是散落文件）。

        判定某个目录 d（深度从 src 算起，顶层条目深度为 1）是否为“单元根目录”：
            - depth(d) == eff_depth(d.split('/'))
              即该目录恰好位于其所在分支应有的单元深度上；或
            - depth(d) <  eff_depth(...) 且该目录没有子目录（has_subdir 为假）
              即目录比预期单元深度浅，但已经是叶子（没有再往下细分的必要）。
        一旦某目录被选为单元根，它的所有子孙目录都不会再被单独选为单元根（避免嵌套重复）。
        不落在任何单元根目录内的文件，各自单独成为一个“散落文件单元”（loose unit）。

    参数：
        src (str): 源目录路径。
        eff_depth (Callable[[list[str]], int]): 由调用方提供的函数，输入路径分段
            （parts，例如 ["01_物料手册", "华为"]），返回该分支应使用的单元深度。
    返回：
        list[tuple[str, int]]: [(单元的 posix 相对路径, 该单元内的文件数量), ...]。
    """
    dirs, files = walk(src)
    dirset = set(dirs)

    def has_subdir(d):
        """判断目录 d 是否含有直接子目录（只看深度恰好 +1 的那一层）。"""
        pre, dd = d + "/", _depth(d) + 1
        return any(x.startswith(pre) and _depth(x) == dd for x in dirset)

    roots = set()
    for d in sorted(dirs, key=_depth):
        # 已经被更浅的单元根覆盖的子目录，直接跳过，避免重复/嵌套。
        if any(d == u or d.startswith(u + "/") for u in roots):
            continue
        dd, ed = _depth(d), eff_depth(d.split("/"))
        if dd == ed or (dd < ed and not has_subdir(d)):
            roots.add(d)

    # 按深度从深到浅排序，这样匹配文件所属单元时，优先匹配更具体（更深）的单元根。
    roots_sorted = sorted(roots, key=lambda x: -_depth(x))
    cnt, loose = defaultdict(int), []
    for f in files:
        r = next((u for u in roots_sorted if f == u or f.startswith(u + "/")), None)
        if r:
            cnt[r] += 1
        else:
            loose.append(f)
    units = [(u, cnt.get(u, 0)) for u in roots] + [(f, 1) for f in loose]
    return units


def build_rows(units, classify):
    """对每个单元调用 classify() 函数进行分类，生成用于写计划文件/审阅页面的行数据。

    说明：
        - classify(src) 由调用方（分类驱动脚本）提供，返回 (leaf, status, note) 三元组：
          leaf 为目标叶子目录，status 为 "normal"（确定）或 "uncertain"（待确认），
          note 为附加说明（不确定的原因等）。
        - 结果按 src（源单元路径）字母序排序，便于生成稳定、可读的计划文件。

    参数：
        units (list[tuple[str, int]]): enumerate_units() 返回的单元列表。
        classify (Callable[[str], tuple[str, str, str]]): 分类函数。
    返回：
        list[dict]: 每个元素形如 {"src", "leaf", "count", "status", "note"}。
    """
    rows = []
    for src, n in units:
        leaf, status, note = classify(src)
        rows.append({"src": src, "leaf": leaf,
                     "count": n, "status": status, "note": note})
    rows.sort(key=lambda r: r["src"])
    return rows


def write_plan(rows, path, src_root, dst_root):
    """把分类结果 rows 写成人类可读的移动计划文本文件（*_文件分类移动计划.txt）。

    说明：
        文件头两行写明源目录根/目标目录根，以及格式说明；正文每个单元占一行，
        格式为：`源单元  =>  目标叶子   （N 文件）`，若该行 status 为 uncertain，
        则额外追加 `[待确认：原因]` 标记，供人工在审阅阶段重点关注。

    参数：
        rows (list[dict]): build_rows() 生成的行数据。
        path (str): 输出的计划文本文件路径。
        src_root (str): 源目录根路径（写入文件头，供后续脚本/展示使用）。
        dst_root (str): 目标目录根路径（写入文件头）。
    返回：
        None（直接写文件）。
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"源目录根：{src_root}    目标目录根：{dst_root}\n")
        f.write("粒度：整包/文件夹为单位（软件/驱动/库/整包不拆）。"
                "格式：源单元  =>  目标叶子   （文件数）[待确认]\n")
        f.write("=" * 90 + "\n")
        for r in rows:
            line = f'{r["src"]}  =>  {r["leaf"]}   （{r["count"]} 文件）'
            if r["status"] == "uncertain":
                line += f'   [待确认：{r["note"]}]'
            f.write(line + "\n")


def verify(rows, src, dst):
    """验收关卡（acceptance gate）：检查分类结果是否完整、合法、无重复。

    说明，返回结果中各字段含义：
        - total_files / covered_files：源目录实际文件总数 / 计划中各单元文件数之和；
          两者相等（coverage_ok=True）才说明“每个文件都被覆盖、且只被计入一次”。
        - invalid_leaves：计划中出现的、但在目标树中并不是真实叶子目录的目标（非法目标）。
          匹配时忽略大小写与路径分隔符差异（"\\" 与 "/" 视为等价），对 Windows 更友好。
        - duplicate_units：出现了多次的源单元路径（理论上不应重复，重复说明枚举或合并逻辑有问题）。
        - uncertain：status 为 "uncertain" 的单元数量（待人工复核的数量）。
        以上列表均为空、且 coverage_ok 为 True，才算通过验收。

        叶子合法性用 `stable_leaf_dirs(dst)`（可信清单）校验，而不是实时重新扫描
        dst——避免目标树里已经存在的、之前分类挪进去的内容被误判成叶子/非叶子
        （见 `stable_leaf_dirs` 的说明）。

    参数：
        rows (list[dict]): build_rows() 生成（或从 units.json 读取）的行数据。
        src (str): 源目录路径。
        dst (str): 目标目录路径。
    返回：
        dict: 包含 total_files/covered_files/coverage_ok/invalid_leaves/duplicate_units/uncertain。
    """
    _, files = walk(src)
    # 叶子目录匹配时忽略大小写与分隔符差异（对 Windows 更友好）：
    # 目标写成 `A\B` 或 `a/b`，只要真实叶子是 `A/B`，都应校验通过。
    leaves = {l.replace("\\", "/").lower() for l in stable_leaf_dirs(dst)}
    key = lambda leaf: leaf.replace("\\", "/").lower()
    covered = sum(r["count"] for r in rows)
    srcs = [r["src"] for r in rows]
    return {
        "total_files": len(files),
        "covered_files": covered,
        "coverage_ok": covered == len(files),
        "invalid_leaves": sorted({r["leaf"] for r in rows if key(r["leaf"]) not in leaves}),
        "duplicate_units": [s for s, c in Counter(srcs).items() if c > 1],
        "uncertain": sum(1 for r in rows if r["status"] == "uncertain"),
    }


def dump_json(rows, path):
    """把行数据 rows 以 JSON 格式写入 path（供 build_review_html.py / reclassify.py 等读取）。"""
    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
