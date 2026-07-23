"""Roadmap 存储 —— 加载 modules/*.md 与 manifest。"""

from __future__ import annotations

import os
import re
from typing import Any

import yaml

from common import SerializeUtil

from .moduleSpec import ModuleSpec

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


class RoadmapStore:
    """从 roadmap 目录加载模块规格。"""

    def __init__(self, roadmapDir: str, repoRoot: str) -> None:
        self.roadmapDir = os.path.abspath(roadmapDir)
        self.repoRoot = os.path.abspath(repoRoot)
        self.modulesDir = os.path.join(self.roadmapDir, "modules")
        self.manifestPath = os.path.join(self.roadmapDir, "_meta", "manifest.json")
        self.indexPath = os.path.join(self.roadmapDir, "INDEX.md")

    def LoadModules(self) -> list[ModuleSpec]:
        """加载 modules/ 下全部模块页。"""
        if not os.path.isdir(self.modulesDir):
            return []

        modules: list[ModuleSpec] = []
        for name in sorted(os.listdir(self.modulesDir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(self.modulesDir, name)
            modules.append(self._LoadModuleFile(path))
        return modules

    def LoadManifest(self) -> dict[str, Any]:
        """读取指纹 manifest；不存在则空 dict。"""
        if not os.path.isfile(self.manifestPath):
            return {"modules": {}}
        with open(self.manifestPath, "r", encoding="utf-8") as f:
            data = SerializeUtil.FromJson(f.read())
        if not isinstance(data, dict):
            return {"modules": {}}
        data.setdefault("modules", {})
        return data

    def SaveManifest(self, manifest: dict[str, Any]) -> None:
        """写入 manifest.json。"""
        metaDir = os.path.dirname(self.manifestPath)
        os.makedirs(metaDir, exist_ok=True)
        with open(self.manifestPath, "w", encoding="utf-8") as f:
            f.write(SerializeUtil.ToJson(manifest, indent=2))
            f.write("\n")

    def ResolveRootPath(self, root: str) -> str:
        """将模块 root 转为绝对路径（相对 repoRoot）。"""
        if os.path.isabs(root):
            return root
        return os.path.normpath(os.path.join(self.repoRoot, root))

    def _LoadModuleFile(self, path: str) -> ModuleSpec:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        meta: dict[str, Any] = {}
        body = text
        match = _FRONT_MATTER_RE.match(text)
        if match:
            meta = yaml.safe_load(match.group(1)) or {}
            body = match.group(2).strip()

        moduleId = str(meta.get("id") or os.path.splitext(os.path.basename(path))[0])
        title = str(meta.get("title") or moduleId)
        aliases = _AsStrList(meta.get("aliases"))
        roots = _AsStrList(meta.get("roots"))
        entrypoints = _AsStrList(meta.get("entrypoints"))
        related = _AsStrList(meta.get("related"))
        summary = str(meta.get("summary") or "")

        return ModuleSpec(
            id=moduleId,
            title=title,
            aliases=aliases,
            roots=roots,
            entrypoints=entrypoints,
            related=related,
            summary=summary,
            body=body,
            sourcePath=path,
        )


def _AsStrList(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()]
