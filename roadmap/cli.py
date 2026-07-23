"""Roadmap CLI —— 外部 Unity/C# 仓模块导航 + 范围内 grep。

命令:
  init            创建 roadmap 骨架
  resolve         描述 → 模块 + roots
  grep            在命中模块 roots 内 rg
  status          对比指纹（不写盘）
  refresh         重算并保存指纹
  suggest-asmdef  扫描 .asmdef 输出候选模块
  list            列出已配置模块

示例:
  python -m roadmap init --repo D:/Game --roadmap D:/Game/.roadmap
  python -m roadmap resolve "结算挂了" --repo D:/Game --roadmap D:/Game/.roadmap
  python -m roadmap grep "timeout" --module settlement --repo D:/Game
"""

from __future__ import annotations

import argparse
import os
import sys

from .fingerprint import FingerprintService
from .initRoadmap import InitRoadmap, RebuildIndex, WriteModuleDraft
from .resolver import ModuleResolver
from .roadmapStore import RoadmapStore
from .scopedGrep import ScopedGrep
from .unityScan import UnityAsmdefScanner


def Main(argv: list[str] | None = None) -> int:
    parser = _BuildParser()
    args = parser.parse_args(argv)
    handler = {
        "init": _CmdInit,
        "resolve": _CmdResolve,
        "grep": _CmdGrep,
        "status": _CmdStatus,
        "refresh": _CmdRefresh,
        "suggest-asmdef": _CmdSuggestAsmdef,
        "suggest-scripts": _CmdSuggestScripts,
        "list": _CmdList,
    }.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


def _BuildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m roadmap",
        description="Unity/C# Code Roadmap: module boundaries + scoped grep",
    )
    sub = parser.add_subparsers(dest="command")

    pInit = sub.add_parser("init", help="Create roadmap skeleton")
    _AddRepoArgs(pInit)
    pInit.add_argument("--force", action="store_true")

    pResolve = sub.add_parser("resolve", help="Map a bug description to modules")
    _AddRepoArgs(pResolve)
    pResolve.add_argument("query", help="Natural language description")
    pResolve.add_argument("--top", type=int, default=3)
    pResolve.add_argument("--no-related", action="store_true")

    pGrep = sub.add_parser("grep", help="rg inside resolved / specified module roots")
    _AddRepoArgs(pGrep)
    pGrep.add_argument("pattern", help="ripgrep pattern")
    pGrep.add_argument("--module", action="append", default=[], help="Module id (repeatable)")
    pGrep.add_argument("--query", default="", help="Or resolve from description")
    pGrep.add_argument("--glob", default="*.cs", help="rg --glob (Unity default *.cs; local py: *.py)")
    pGrep.add_argument("--max-count", type=int, default=20)
    pGrep.add_argument("--context", type=int, default=0)
    pGrep.add_argument("--no-related", action="store_true", help="Do not expand related modules")

    pStatus = sub.add_parser("status", help="Fingerprint status without writing")
    _AddRepoArgs(pStatus)

    pRefresh = sub.add_parser("refresh", help="Recompute fingerprints and save manifest")
    _AddRepoArgs(pRefresh)

    pSuggest = sub.add_parser("suggest-asmdef", help="Suggest modules from Unity .asmdef")
    _AddRepoArgs(pSuggest)
    pSuggest.add_argument("--write", action="store_true", help="Write draft module markdown")
    pSuggest.add_argument("--limit", type=int, default=100)

    pScripts = sub.add_parser(
        "suggest-scripts",
        help="Suggest modules from Assets/Scripts subfolders (no asmdef projects)",
    )
    _AddRepoArgs(pScripts)
    pScripts.add_argument("--write", action="store_true")
    pScripts.add_argument("--scripts", default="Assets/Scripts")

    pList = sub.add_parser("list", help="List configured modules")
    _AddRepoArgs(pList)

    return parser


def _AddRepoArgs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        default=".",
        help="Unity / code repository root (default: cwd)",
    )
    parser.add_argument(
        "--roadmap",
        default="",
        help="Roadmap dir (default: <repo>/.roadmap)",
    )


def _Paths(args: argparse.Namespace) -> tuple[str, str]:
    repo = os.path.abspath(args.repo)
    roadmap = os.path.abspath(args.roadmap) if args.roadmap else os.path.join(repo, ".roadmap")
    return repo, roadmap


def _CmdInit(args: argparse.Namespace) -> int:
    repo, roadmap = _Paths(args)
    path = InitRoadmap(roadmap, force=args.force)
    print(f"roadmap ready: {path}")
    print(f"repo root:     {repo}")
    print("next: add modules under modules/*.md  or  run suggest-asmdef --write")
    return 0


def _CmdList(args: argparse.Namespace) -> int:
    store, modules = _Load(args)
    if not modules:
        print("no modules. run init + add modules/*.md")
        return 1
    for m in modules:
        roots = ", ".join(m.roots) if m.roots else "(no roots)"
        print(f"- {m.id:24} {m.title:20} roots={roots}")
    print(f"\n{len(modules)} modules | roadmap={store.roadmapDir}")
    return 0


def _CmdResolve(args: argparse.Namespace) -> int:
    store, modules = _Load(args)
    if not modules:
        print("no modules configured", file=sys.stderr)
        return 1
    resolver = ModuleResolver(modules)
    hits = resolver.Resolve(args.query, topK=args.top, expandRelated=not args.no_related)
    if not hits:
        print(f"no module matched: {args.query}")
        return 1
    roots = resolver.CollectRoots(hits, store.ResolveRootPath)
    print(f"query: {args.query}\n")
    for hit in hits:
        print(f"[{hit.score:.1f}] {hit.module.id}  ({hit.module.title})")
        print(f"       reason: {hit.reason}")
        if hit.module.summary:
            print(f"       summary: {hit.module.summary}")
        for root in hit.module.roots:
            absRoot = store.ResolveRootPath(root)
            mark = "OK" if os.path.exists(absRoot) else "MISSING"
            print(f"       root[{mark}]: {root}")
        if hit.module.entrypoints:
            print(f"       entry: {', '.join(hit.module.entrypoints)}")
        print()
    print("search roots:")
    for r in roots:
        print(f"  {r}")
    return 0


def _CmdGrep(args: argparse.Namespace) -> int:
    store, modules = _Load(args)
    resolver = ModuleResolver(modules)
    hits = []
    if args.module:
        for mid in args.module:
            m = resolver.GetById(mid)
            if m is None:
                print(f"unknown module: {mid}", file=sys.stderr)
                return 1
            from .resolver import ResolveHit

            hits.append(ResolveHit(module=m, score=100.0, reason="cli --module"))
    elif args.query:
        hits = resolver.Resolve(
            args.query,
            topK=3,
            expandRelated=not args.no_related,
        )
        if not hits:
            print(f"no module matched: {args.query}", file=sys.stderr)
            return 1
    else:
        print("provide --module or --query", file=sys.stderr)
        return 2

    roots = resolver.CollectRoots(hits, store.ResolveRootPath)
    print("modules: " + ", ".join(h.module.id for h in hits))
    print("roots:")
    for r in roots:
        print(f"  {r}")
    print()

    grepper = ScopedGrep()
    result = grepper.Search(
        pattern=args.pattern,
        roots=roots,
        glob=args.glob,
        maxCount=args.max_count,
        context=args.context,
    )
    sys.stdout.write(result.output)
    return 0 if result.ok else 1


def _CmdStatus(args: argparse.Namespace) -> int:
    store, modules = _Load(args)
    if not modules:
        print("no modules")
        return 1
    diffs = FingerprintService(store).Status(modules)
    return _PrintDiffs(diffs)


def _CmdRefresh(args: argparse.Namespace) -> int:
    store, modules = _Load(args)
    if not modules:
        print("no modules")
        return 1
    diffs = FingerprintService(store).RefreshAll(modules)
    RebuildIndex(store.roadmapDir, modules)
    print(f"manifest written: {store.manifestPath}")
    return _PrintDiffs(diffs)


def _CmdSuggestAsmdef(args: argparse.Namespace) -> int:
    repo, roadmap = _Paths(args)
    InitRoadmap(roadmap)
    suggestions = UnityAsmdefScanner(repo).Scan(limit=args.limit)
    if not suggestions:
        print("no .asmdef found under Assets (many tutorial projects put code in Assembly-CSharp)")
        print("try: python -m roadmap suggest-scripts --write ...")
        return 0
    for s in suggestions:
        print(f"- {s.id:32} root={s.root}  source={s.source}")
        if args.write:
            WriteModuleDraft(
                roadmap,
                moduleId=s.id,
                title=s.title,
                roots=[s.root],
                aliases=s.aliases,
                summary=f"Unity asmdef {s.title}",
            )
    if args.write:
        store = RoadmapStore(roadmap, repo)
        RebuildIndex(roadmap, store.LoadModules())
        print(f"\nwrote drafts under {os.path.join(roadmap, 'modules')}")
    return 0


def _CmdSuggestScripts(args: argparse.Namespace) -> int:
    repo, roadmap = _Paths(args)
    InitRoadmap(roadmap)
    suggestions = UnityAsmdefScanner(repo).ScanScriptFolders(scriptsRel=args.scripts)
    if not suggestions:
        print(f"no folder: {args.scripts}")
        return 1
    for s in suggestions:
        print(f"- {s.id:32} root={s.root}  aliases={','.join(s.aliases)}")
        if args.write:
            WriteModuleDraft(
                roadmap,
                moduleId=s.id,
                title=s.title,
                roots=[s.root],
                aliases=s.aliases,
                summary=f"Scripts folder {s.root}",
            )
    if args.write:
        store = RoadmapStore(roadmap, repo)
        RebuildIndex(roadmap, store.LoadModules())
        # wire a few related links for this tutorial project
        _PatchTutorialRelated(roadmap)
        RebuildIndex(roadmap, store.LoadModules())
        print(f"\nwrote drafts under {os.path.join(roadmap, 'modules')}")
    return 0


def _PatchTutorialRelated(roadmapDir: str) -> None:
    """为本教程仓补 related（敌人↔对象池、玩家↔玩法根）。"""
    patches = {
        "enemy": ["objectpool", "scripts-root"],
        "player": ["scripts-root"],
        "player-1": ["scripts-root", "player"],
        "objectpool": ["enemy", "scripts-root"],
        "level-generation": ["large-level-procedural-generation"],
        "large-level-procedural-generation": ["level-generation", "enemy"],
        "scripts-root": ["enemy", "player", "objectpool"],
    }
    modulesDir = os.path.join(roadmapDir, "modules")
    for moduleId, related in patches.items():
        path = os.path.join(modulesDir, f"{moduleId}.md")
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if "related:\n  - " in text and "related: []" not in text:
            continue
        relatedBlock = "related:\n" + "\n".join(f"  - {r}" for r in related)
        text = text.replace("related: []", relatedBlock, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def _Load(args: argparse.Namespace) -> tuple[RoadmapStore, list]:
    repo, roadmap = _Paths(args)
    store = RoadmapStore(roadmap, repo)
    return store, store.LoadModules()


def _PrintDiffs(diffs) -> int:
    counts = {"ok": 0, "new": 0, "drifted": 0, "missing_roots": 0, "vanished": 0}
    for d in diffs:
        counts[d.status] = counts.get(d.status, 0) + 1
        cur = d.current
        extra = ""
        if cur is not None:
            extra = f" files={cur.fileCount} csish={cur.codeFileCount}"
        print(f"[{d.status:13}] {d.moduleId:24} {d.detail}{extra}")
    print(
        "\nsummary: "
        + ", ".join(f"{k}={v}" for k, v in counts.items() if v)
    )
    # missing_roots 视为失败态
    return 1 if counts.get("missing_roots") else 0


if __name__ == "__main__":
    raise SystemExit(Main())
