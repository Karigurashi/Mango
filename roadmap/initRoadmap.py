"""初始化 Roadmap 目录骨架。"""

from __future__ import annotations

import os


INDEX_TEMPLATE = """# Code Roadmap

面向模糊报障（如「结算挂了」）的模块导航索引。

用法：
1. 用描述匹配模块（aliases）
2. 仅在模块 `roots` 内 grep
3. 需要时再打开 `related` 模块

## 模块列表

{moduleList}

## Unity 提示

- 优先用 `.asmdef` 所在目录作为 `roots`
- 忽略 `Library/`、`Temp/`、`Logs/` 等生成目录
- 本 INDEX 可手写维护；`suggest-asmdef` 仅生成草稿建议
"""

MODULE_TEMPLATE = """---
id: {id}
title: {title}
aliases:
{aliases}
roots:
{roots}
entrypoints: []
related: []
summary: "{summary}"
---

## 职责

（一句话说明本模块做什么）

## 结构

- 入口：
- 分层：

## 备注

"""


def InitRoadmap(roadmapDir: str, force: bool = False) -> str:
    """创建 roadmap 目录结构；已存在且非 force 则跳过。"""
    roadmapDir = os.path.abspath(roadmapDir)
    modulesDir = os.path.join(roadmapDir, "modules")
    metaDir = os.path.join(roadmapDir, "_meta")
    indexPath = os.path.join(roadmapDir, "INDEX.md")

    if os.path.exists(indexPath) and not force:
        return roadmapDir

    os.makedirs(modulesDir, exist_ok=True)
    os.makedirs(metaDir, exist_ok=True)

    if not os.path.exists(indexPath) or force:
        with open(indexPath, "w", encoding="utf-8") as f:
            f.write(INDEX_TEMPLATE.format(moduleList="- （在 modules/ 下添加模块页）"))
            f.write("\n")

    gitignore = os.path.join(metaDir, ".gitignore")
    if not os.path.exists(gitignore):
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write("# fingerprints are local; keep module markdown in VCS\n")
            f.write("manifest.json\n")

    return roadmapDir


def WriteModuleDraft(
    roadmapDir: str,
    moduleId: str,
    title: str,
    roots: list[str],
    aliases: list[str] | None = None,
    summary: str = "",
    overwrite: bool = False,
) -> str:
    """写入单个模块 md 草稿。"""
    modulesDir = os.path.join(os.path.abspath(roadmapDir), "modules")
    os.makedirs(modulesDir, exist_ok=True)
    path = os.path.join(modulesDir, f"{moduleId}.md")
    if os.path.exists(path) and not overwrite:
        return path

    aliasLines = "\n".join(f"  - {a}" for a in (aliases or [title]))
    rootLines = "\n".join(f"  - {r}" for r in roots) if roots else "  - ."
    text = MODULE_TEMPLATE.format(
        id=moduleId,
        title=title,
        aliases=aliasLines,
        roots=rootLines,
        summary=summary.replace('"', "'"),
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def RebuildIndex(roadmapDir: str, modules: list) -> None:
    """根据已加载模块重写 INDEX 列表段（简单全量重写）。"""
    lines = []
    for m in modules:
        alias = ", ".join(m.aliases[:5]) if m.aliases else ""
        extra = f" — `{alias}`" if alias else ""
        lines.append(f"- [[{m.id}]] {m.title}{extra}")
    moduleList = "\n".join(lines) if lines else "- （空）"
    path = os.path.join(os.path.abspath(roadmapDir), "INDEX.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(INDEX_TEMPLATE.format(moduleList=moduleList))
        f.write("\n")
