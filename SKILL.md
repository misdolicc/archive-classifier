---
name: archive-classifier
description: Classify a large or messy source folder of files into an existing target taxonomy directory tree and produce a review-ready move plan (no real moves by default), plus a single-file HTML review tool. Use when the user asks to sort / organize / 归类 / 分类 files or a data dump into a destination folder structure — especially at scale (thousands+ files, software / driver / library / equipment dumps) where package-level grouping, leaf-only placement, and a reviewable move plan are needed.
---

# Archive Classifier

Turn a raw source folder into a **move plan** that maps its contents into an existing
**target taxonomy tree**, then hand the user a self-contained **HTML review tool**. Do NOT
move files unless explicitly asked — produce a plan first.

## Core rules

1. **Files go only into LEAF nodes** of the target tree (directories with no sub-directories).
   Never place a file/unit in an intermediate node.
2. **Keep groups together.** A datasheet + its 3D/2D model, a multi-part/multi-language
   manual, a vendor's product folder, a software package — one unit, one destination.
3. **Package-level granularity for dumps.** Software installs, SDKs, driver/part libraries,
   runtime-data dumps (`.ors/.res/.dll/.bin`, installers, logs), and whole-equipment folders
   move as **one unit** — never explode them file-by-file.
4. **Inspect before guessing, whenever structure or naming alone doesn't resolve it.** Two
   decisions this applies to:
   (a) **unit depth** (`eff_depth`) — don't assign one depth to an entire top-level branch
   sight-unseen; sample its real shape first with `units_lib.preview_depth(src, top)` (shows,
   per depth, sample dirs + whether each still has sub-dirs) and pick the depth where dirs are
   actually whole, undivided packages. Branches aren't always uniform — `eff_depth(parts)` can
   key off `parts[1]`/deeper, not just `parts[0]`, when different sub-trees under the same top
   folder need different depths;
   (b) **classify() targets** — a path/filename that's an opaque code or generic name (and would
   otherwise fall to `uncertain`/`FALLBACK_LEAF`) is worth opening — use judgment per unit: open
   a representative file (Read tool; extract text from PDF/Word first if needed) when it would
   likely resolve the ambiguity, skip it when the parent folder/vendor context already gives
   enough signal, and skip it for whole software/driver/library dumps (rule 3 — they're one unit
   regardless of what's inside).
   Both are judgment calls you make inline, once, while authoring/refining `eff_depth` and
   `classify()` in the current session — not a separate automated per-file/per-directory AI
   pipeline (cost/time do not scale to opening thousands of binaries or re-deriving depth per
   directory at runtime; see Workflow steps 3 and 6).
5. **Flag uncertainty.** Anything that lands on a generic `其他 / Other` leaf, or a category
   with no clean home, gets `status=uncertain` with a short reason for human review.
6. **Output next to the source or on the project drive**, not a temp dir.
7. **Leaf discovery must not be fooled by content already moved into the target tree.** A live
   re-scan (`leaf_dirs`) defines a leaf as "a dir with no sub-dirs" — but once a unit has been
   moved into a leaf by `move_plan.py` (or by hand) in a *previous* round, that leaf now has a
   sub-dir (the moved unit), so a fresh re-scan wrongly demotes it, and — if the moved unit
   itself has no sub-dirs — wrongly promotes the moved unit into a brand-new "leaf". Always
   resolve leaves via `units_lib.stable_leaf_dirs(dst)`, which reads a persisted manifest
   (`dst/.archive_classifier_leaves.json`) instead of re-deriving structure from the live,
   possibly content-mixed tree; it self-bootstraps from a live scan only the first time a given
   target tree is used (ideally while it's still a clean skeleton). When you deliberately create
   a **new** real leaf folder (rule 4/Workflow step 4, or `move_plan.py`'s
   `CREATE_MISSING_LEAVES`), register it with `units_lib.add_leaves(dst, new_leaf_path)`
   immediately — that is the only sound way to tell "a genuine new category" apart from
   "content that happens to look like one"; never re-derive the whole manifest from a live
   scan once real content has been moved in.

## Workflow

1. **Recon (never list every file for big sets).** Get top-level dir file counts + total;
   find where the mass concentrates; detect software/data dumps. See
   `scripts/units_lib.py:summarize`.
2. **Discover target leaves.** `stable_leaf_dirs(dst)` → the only valid destinations (see rule 7;
   this is a persisted, content-move-proof list, not a live re-scan).
3. **Decide granularity — ASK when scale is large/mixed** (use AskUserQuestion):
   file-level for curated document sets (hundreds); package/folder-level for
   thousands+ / software / equipment dumps. Recommend package-level for dumps.
   Before fixing a depth number per top-level branch, sample its actual shape with
   `units_lib.preview_depth(src, top)` (see Core rule 4a) rather than guessing from the
   branch name alone.
4. **Missing categories — ASK before inventing.** If the source holds material with no home
   in the target tree (e.g. competitor equipment), propose a new top-level category, confirm,
   then create the new leaf folders in the target tree and immediately register them with
   `units_lib.add_leaves(dst, *new_leaf_paths)` (rule 7) so plan targets are real, discoverable
   leaves.
5. **Confirm ambiguous category semantics** with the user and record them (memory), e.g.
   "产品信息资料 = the DUT products we build test benches for, not our/competitor equipment".
6. **Classify.** Copy `scripts/classify_example.py` to a project driver `run.py`, then edit
   its 3 marked sections: paths + `FALLBACK_LEAF`, `eff_depth` (unit depth per top folder), and
   `classify(relpath) -> (leaf, status, note)` — ordered keyword rules, first match wins,
   scoped by top-level category, fall back to `FALLBACK_LEAF` (a **real** catch-all leaf in the
   target tree, e.g. a `其他`/`Other`/`待归档` folder) with `status="uncertain"`.
   Before finalizing rules for units that path/filename alone can't resolve (rule 4), open a
   representative file yourself (Read tool) to inform the rule or the `note` you leave — this
   is your judgment call per unit/cluster, done once while authoring `classify()`, not a
   per-file automated step. Run it; it enumerates units + counts, writes the plan +
   `*_units.json`, and self-verifies coverage.
7. **Plan format** (`units_lib.write_plan`): one line per unit
   `源单元  =>  目标叶子   （N 文件）[待确认：原因]`, plus a `*_units.json`
   (`[{src, leaf, count, status, note}]`) that drives the review tool.
8. **Verify** (the driver prints it, or run `scripts/verify_coverage.py`): coverage
   (`covered == total`), 0 invalid leaves, 0 duplicate source units. Fix until PASS.
9. **Build the review tool** — edit the constants at the top of
   `scripts/build_review_html.py` (`UNITS/SRC/DST/OUT/NAME/BIG/COPY_BACKEND`; `SRC`+`DST` fill
   the export header, `NAME` labels exports and namespaces the browser's saved progress, `BIG` =
   the large-package file threshold, default 500) and run it (or import `units_lib.stable_leaf_dirs`
   + fill `templates/review.html` in the driver). It fills the `__LEAVES__`/`__UNITS__`/`__META__`
   placeholders, and — when `COPY_BACKEND` is true (default) — also copies
   `scripts/review_server.py` next to `OUT` (skipped if that would copy onto itself), so the
   workspace folder is self-contained: HTML + `units.json` + plan + backend, no need to reach
   back into the skill's own `scripts/` dir. This happens on every build, including rebuilds
   triggered by `reclassify.py`. Single file, no deps: search, group by
   source/target, filter (待确认 / 已改 / 大包>BIG / 待重分类 / 审阅状态), edit target with leaf
   autocomplete + red-border validation, mark-reviewed, per-row **需要重新分类** checkbox,
   export txt+CSV, progress in localStorage. Works standalone (double-click); the two features
   below light up only when it's served by the backend.
10. **Optional backend + re-classify loop.** Serve the page with `scripts/review_server.py HTML`
    (binds 127.0.0.1, reads srcRoot/name from the HTML's `__META__`). Then: (a) clicking a source
    unit opens it **read-only** in the OS default viewer (`GET /open`, path confined to srcRoot);
    (b) ticking **需要重新分类** on wrong rows and hitting **提交待重分类** POSTs them to
    `<name>_reclassify_queue.json`. To re-classify: improve the rules in `run.py` (same
    `classify()` method), then run `scripts/reclassify.py` — it re-runs `classify()` on **only**
    the queued units, updates `units.json` (new leaf/status/note + bumped `rev`) and rebuilds the
    HTML. On refresh the bumped `rev` makes the page drop stale local state for those units so they
    show the fresh target and re-enter review. Without the backend, 提交待重分类 downloads the same
    queue JSON to feed `reclassify.py`.
11. **Don't move by default.** After the user has reviewed and exported the plan, run
    `scripts/move_plan.py` to apply it — it reads the reviewed `…_已审阅.txt`, and for each
    `源单元 => 目标叶子` line places the **whole unit** (package folder or loose file) into the
    leaf. Copy by default (source preserved), conflict-rename (` (2)`…, never overwrite/merge),
    real leaves validated against `stable_leaf_dirs` (rule 7), and **DRY_RUN=True first** —
    preview + log, then flip to apply. If `CREATE_MISSING_LEAVES=True` makes it create a leaf,
    it auto-registers that leaf via `add_leaves` so it isn't lost on the next round.

## Files
- `scripts/units_lib.py` — walk, leaf discovery (`leaf_dirs` raw scan, `stable_leaf_dirs`
  manifest-backed lookup, `add_leaves` to register genuinely new leaves — rule 7), unit
  enumeration (leaf-only, package-aware), depth-shape preview (`preview_depth`, to inform
  `eff_depth`), file counting, plan writer, verifier. Import this; write only `eff_depth` +
  `classify`.
- `scripts/classify_example.py` — runnable skeleton showing eff_depth + a keyword ruleset.
- `scripts/build_review_html.py` — fills `templates/review.html` from units.json + leaf list;
  also copies `scripts/review_server.py` next to the output HTML (`COPY_BACKEND`, default on).
- `scripts/verify_coverage.py` — coverage / leaf-validity / duplicate check.
- `scripts/move_plan.py` — apply a reviewed plan: whole-unit copy/move into leaves,
  conflict-rename, leaf validation, dry-run-first + log.
- `scripts/review_server.py` — optional 127.0.0.1 backend: serves the HTML, `/open` (read-only
  open a source unit), `/reclassify-queue` (capture 需要重新分类 marks).
- `scripts/reclassify.py` — re-run `classify()` on the queued units, merge new leaf/status/note
  (+ bump `rev`) into units.json, rebuild the HTML.
- `templates/review.html` — JSON-driven review UI (`__LEAVES__`, `__UNITS__`, `__META__` placeholders).

## Notes
- Paths use posix `/` as the single canonical separator (display + matching); it is valid on
  Windows too. Leaf matching in the review UI is sep-insensitive (`\`↔`/`) and case-insensitive.
- **Windows + CJK only** (skip on Linux/macOS or ASCII-only data): run Python with
  `PYTHONIOENCODING=utf-8` for CJK console output, and note that Git Bash mangles 中文 in
  command-line args AND here-docs — so put CJK paths in **in-file constants** (a UTF-8 `run.py`
  written with the Write tool) and run the file, rather than passing 中文 on the CLI or inside
  a `bash <<'PY'` here-doc.
- Coverage is the acceptance gate: `sum(unit counts) == total files walked`, 0 invalid leaves.
- The HTML stays self-contained; the backend is optional. Click-to-open and re-classify submit
  need it served over http (`review_server.py`); a raw `file://` page degrades gracefully
  (open → hint, submit → downloads the queue JSON). Re-classify uses a per-unit `rev` in the
  embedded units: bumping it (done by `reclassify.py`) makes the page reset those units' local
  review state on the next refresh, so they re-enter review with the fresh target.
- Default output = a plan only. Apply it only when asked, via `scripts/move_plan.py`
  (`MODE="copy"`/`"move"`, `DRY_RUN=True` first): whole-unit into leaf + conflict-rename + a
  log; never per-file for dump packages.
- The target tree gets one small hidden file: `dst/.archive_classifier_leaves.json` (the leaf
  manifest, rule 7). It's created the first time `stable_leaf_dirs`/`verify` touches a given
  `dst`. If a target tree already had content moved into it before this manifest existed (by
  hand, or by an older run of this skill), the first bootstrap snapshot bakes in whatever mixed
  state exists at that moment — review the generated JSON once in that case, or clear it and
  re-bootstrap once you've confirmed the tree is a clean skeleton again.
