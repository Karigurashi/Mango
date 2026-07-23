"""模块指纹 —— 增量检测 roots 是否漂移。"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any

from .moduleSpec import ModuleSpec
from .roadmapStore import RoadmapStore

_CODE_EXTS = {".cs", ".asmdef", ".csproj", ".py"}


@dataclass
class ModuleFingerprint:
    """单模块指纹快照。"""

    moduleId: str
    fileCount: int
    codeFileCount: int
    sampleHash: str
    missingRoots: list[str]
    checkedAt: float

    def ToDict(self) -> dict[str, Any]:
        return {
            "moduleId": self.moduleId,
            "fileCount": self.fileCount,
            "codeFileCount": self.codeFileCount,
            "sampleHash": self.sampleHash,
            "missingRoots": self.missingRoots,
            "checkedAt": self.checkedAt,
        }

    @staticmethod
    def FromDict(data: dict[str, Any]) -> "ModuleFingerprint":
        return ModuleFingerprint(
            moduleId=str(data.get("moduleId") or ""),
            fileCount=int(data.get("fileCount") or 0),
            codeFileCount=int(data.get("codeFileCount") or 0),
            sampleHash=str(data.get("sampleHash") or ""),
            missingRoots=[str(x) for x in (data.get("missingRoots") or [])],
            checkedAt=float(data.get("checkedAt") or 0.0),
        )


@dataclass
class FingerprintDiff:
    """相对上次 manifest 的变化。"""

    moduleId: str
    status: str  # ok | new | missing_roots | drifted | vanished
    detail: str
    current: ModuleFingerprint | None
    previous: ModuleFingerprint | None


class FingerprintService:
    """计算并对比模块 roots 指纹。"""

    def __init__(self, store: RoadmapStore) -> None:
        self._store = store

    def Compute(self, module: ModuleSpec) -> ModuleFingerprint:
        missing: list[str] = []
        relFiles: list[str] = []
        codeCount = 0

        for root in module.roots:
            absRoot = self._store.ResolveRootPath(root)
            if not os.path.exists(absRoot):
                missing.append(root)
                continue
            if os.path.isfile(absRoot):
                rel = os.path.relpath(absRoot, self._store.repoRoot)
                relFiles.append(rel.replace("\\", "/"))
                if os.path.splitext(absRoot)[1].lower() in _CODE_EXTS:
                    codeCount += 1
                continue
            for dirPath, dirNames, fileNames in os.walk(absRoot):
                dirNames[:] = [d for d in dirNames if d not in _SKIP_DIRS and not d.startswith(".")]
                for fileName in fileNames:
                    full = os.path.join(dirPath, fileName)
                    rel = os.path.relpath(full, self._store.repoRoot).replace("\\", "/")
                    relFiles.append(rel)
                    if os.path.splitext(fileName)[1].lower() in _CODE_EXTS:
                        codeCount += 1

        relFiles.sort()
        sample = "\n".join(relFiles[:5000])
        digest = hashlib.sha256(sample.encode("utf-8")).hexdigest()[:16]
        return ModuleFingerprint(
            moduleId=module.id,
            fileCount=len(relFiles),
            codeFileCount=codeCount,
            sampleHash=digest,
            missingRoots=missing,
            checkedAt=time.time(),
        )

    def RefreshAll(self, modules: list[ModuleSpec]) -> list[FingerprintDiff]:
        """重算全部模块指纹并写回 manifest。"""
        manifest = self._store.LoadManifest()
        prevMap = {
            k: ModuleFingerprint.FromDict(v)
            for k, v in (manifest.get("modules") or {}).items()
            if isinstance(v, dict)
        }
        diffs: list[FingerprintDiff] = []
        newMap: dict[str, Any] = {}

        currentIds = {m.id for m in modules}
        for module in modules:
            current = self.Compute(module)
            previous = prevMap.get(module.id)
            diffs.append(self._Diff(module.id, current, previous))
            newMap[module.id] = current.ToDict()

        for oldId, previous in prevMap.items():
            if oldId not in currentIds:
                diffs.append(
                    FingerprintDiff(
                        moduleId=oldId,
                        status="vanished",
                        detail="module file removed from roadmap",
                        current=None,
                        previous=previous,
                    )
                )

        manifest["modules"] = newMap
        manifest["updatedAt"] = time.time()
        manifest["repoRoot"] = self._store.repoRoot
        self._store.SaveManifest(manifest)
        return diffs

    def Status(self, modules: list[ModuleSpec]) -> list[FingerprintDiff]:
        """只对比、不写盘。"""
        manifest = self._store.LoadManifest()
        prevMap = {
            k: ModuleFingerprint.FromDict(v)
            for k, v in (manifest.get("modules") or {}).items()
            if isinstance(v, dict)
        }
        diffs: list[FingerprintDiff] = []
        for module in modules:
            current = self.Compute(module)
            previous = prevMap.get(module.id)
            diffs.append(self._Diff(module.id, current, previous))
        return diffs

    def _Diff(
        self,
        moduleId: str,
        current: ModuleFingerprint,
        previous: ModuleFingerprint | None,
    ) -> FingerprintDiff:
        if current.missingRoots:
            return FingerprintDiff(
                moduleId=moduleId,
                status="missing_roots",
                detail=f"missing: {', '.join(current.missingRoots)}",
                current=current,
                previous=previous,
            )
        if previous is None:
            return FingerprintDiff(
                moduleId=moduleId,
                status="new",
                detail="no previous fingerprint",
                current=current,
                previous=None,
            )
        if previous.sampleHash != current.sampleHash or previous.fileCount != current.fileCount:
            return FingerprintDiff(
                moduleId=moduleId,
                status="drifted",
                detail=(
                    f"files {previous.fileCount}->{current.fileCount}, "
                    f"hash {previous.sampleHash}->{current.sampleHash}"
                ),
                current=current,
                previous=previous,
            )
        return FingerprintDiff(
            moduleId=moduleId,
            status="ok",
            detail="unchanged",
            current=current,
            previous=previous,
        )


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
