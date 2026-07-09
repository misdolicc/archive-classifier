# -*- coding: utf-8 -*-
"""Acceptance gate for a generated plan.

Edit the constants below and run (Git Bash mangles CJK CLI args, so prefer in-file
constants). ASCII-only paths may instead be passed as argv: UNITS SRC DST.
Checks: every source file attributed exactly once, every target is a real leaf,
no duplicate source units. Exits non-zero on failure.

    PYTHONIOENCODING=utf-8 python verify_coverage.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import units_lib as U

# ===== EDIT-ME (or pass 3 ASCII argv) =========================================
UNITS = "./units.json"
SRC   = "./source"
DST   = "./target-tree"

def main():
    """入口函数：读取 units.json 并对分类结果做验收检查，打印报告并按结果设置退出码。

    说明：
        - 优先使用命令行参数（4 个及以上 ASCII 参数：units_path src dst），否则使用
          脚本顶部 EDIT-ME 区域的常量 UNITS/SRC/DST（CJK 路径应写在这里，因为 Git Bash
          会破坏命令行传入的中文参数）。
        - 调用 units_lib.verify() 做核心校验：覆盖率是否 100%、是否存在非法叶子目标、
          是否存在重复的源单元。三项全部通过才算 PASS。
        - 最终以 sys.exit(0 表示通过，1 表示失败) 结束，方便在流水线/脚本中判断是否通过。
    """
    units_path, src, dst = (sys.argv[1:4] if len(sys.argv) >= 4 else (UNITS, SRC, DST))
    rows = json.load(open(units_path, encoding="utf-8"))
    r = U.verify(rows, src, dst)
    print(f"units: {len(rows)}")
    print(f"files covered: {r['covered_files']} / {r['total_files']}  coverage_ok: {r['coverage_ok']}")
    print(f"uncertain units: {r['uncertain']}")
    print(f"invalid leaves: {len(r['invalid_leaves'])}")
    for b in r["invalid_leaves"]:
        print("   INVALID ->", b)
    print(f"duplicate source units: {len(r['duplicate_units'])}")
    for d in r["duplicate_units"]:
        print("   DUP ->", d)
    ok = r["coverage_ok"] and not r["invalid_leaves"] and not r["duplicate_units"]
    print("\nRESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
