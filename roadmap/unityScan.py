"""Unity 辅助 —— 从 .asmdef / Scripts 子目录扫描候选模块草稿。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass
class ModuleSuggestion:
    """候选模块草稿。"""

    id: str
    title: str
    root: str
    source: str
    aliases: list[str]


class UnityAsmdefScanner:
    """扫描仓库中的 .asmdef / Scripts 子目录，生成模块边界建议。"""

    def __init__(self, repoRoot: str) -> None:
        self._repoRoot = os.path.abspath(repoRoot)

    def Scan(self, limit: int = 200) -> list[ModuleSuggestion]:
        suggestions: list[ModuleSuggestion] = []
        for dirPath, dirNames, fileNames in os.walk(self._repoRoot):
            dirNames[:] = [d for d in dirNames if d not in _SKIP_DIRS and not d.startswith(".")]
            for fileName in fileNames:
                if not fileName.endswith(".asmdef"):
                    continue
                full = os.path.join(dirPath, fileName)
                relDir = os.path.relpath(dirPath, self._repoRoot).replace("\\", "/")
                relFile = os.path.relpath(full, self._repoRoot).replace("\\", "/")
                asmName = self._ReadAsmdefName(full) or os.path.splitext(fileName)[0]
                safeId = _SafeId(asmName)
                suggestions.append(
                    ModuleSuggestion(
                        id=safeId,
                        title=asmName,
                        root=relDir if relDir != "." else ".",
                        source=relFile,
                        aliases=[asmName],
                    )
                )
                if len(suggestions) >= limit:
                    return suggestions
        return suggestions

    def ScanScriptFolders(self, scriptsRel: str = "Assets/Scripts") -> list[ModuleSuggestion]:
        """无/少 asmdef 时：按 Assets/Scripts 子目录生成模块建议。"""
        scriptsAbs = os.path.join(self._repoRoot, scriptsRel.replace("/", os.sep))
        if not os.path.isdir(scriptsAbs):
            return []

        suggestions: list[ModuleSuggestion] = []
        topCs = [
            n for n in os.listdir(scriptsAbs)
            if n.endswith(".cs") and os.path.isfile(os.path.join(scriptsAbs, n))
        ]
        if topCs:
            suggestions.append(
                ModuleSuggestion(
                    id="scripts-root",
                    title="Scripts Root",
                    root=scriptsRel.replace("\\", "/"),
                    source=scriptsRel,
                    aliases=["Scripts", "gameplay", "玩法", "战斗", "子弹"],
                )
            )

        for name in sorted(os.listdir(scriptsAbs)):
            full = os.path.join(scriptsAbs, name)
            if not os.path.isdir(full) or name.startswith("."):
                continue
            rel = f"{scriptsRel.rstrip('/')}/{name}".replace("\\", "/")
            safeId = _SafeId(name)
            aliases = [name]
            aliases.extend(_ChineseHints(name))
            suggestions.append(
                ModuleSuggestion(
                    id=safeId,
                    title=name,
                    root=rel,
                    source=rel,
                    aliases=aliases,
                )
            )
        return suggestions

    def _ReadAsmdefName(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            name = data.get("name")
            return str(name) if name else ""
        except (OSError, json.JSONDecodeError, TypeError):
            return ""


def _ChineseHints(folderName: str) -> list[str]:
    key = folderName.lower()
    hints: list[str] = []
    mapping = [
        (("enemy",), ["敌人", "怪", "Enemy"]),
        (("player",), ["玩家", "角色", "Player"]),
        (("level", "floor", "procedural"), ["关卡", "地图", "生成", "Level"]),
        (("pool",), ["对象池", "Pool"]),
        (("scene",), ["场景", "Scene"]),
        (("navmesh", "nav"), ["寻路", "NavMesh"]),
        (("attack", "bullet", "combat"), ["战斗", "攻击", "子弹"]),
    ]
    for keys, values in mapping:
        if any(k in key for k in keys):
            hints.extend(values)
    return hints


def _SafeId(name: str) -> str:
    out: list[str] = []
    for ch in name:
        if ch.isalnum():
            out.append(ch.lower())
        elif ch in (".", "_", "-", " "):
            out.append("-")
    text = "".join(out).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text or "module"


_SKIP_DIRS = {
    "Library",
    "Temp",
    "Obj",
    "obj",
    "bin",
    "Logs",
    "Build",
    "Builds",
    "node_modules",
    "__pycache__",
    ".git",
}
