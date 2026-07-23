"""模块解析 —— 用描述/别名命中 Roadmap 模块。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from .moduleSpec import ModuleSpec


@dataclass
class ResolveHit:
    """一次模块命中结果。"""

    module: ModuleSpec
    score: float
    reason: str


class ModuleResolver:
    """将自然语言描述解析到模块（规则优先，不上全仓 AI）。"""

    def __init__(self, modules: list[ModuleSpec]) -> None:
        self._modules = modules
        self._byId = {m.id.lower(): m for m in modules}

    def Resolve(
        self,
        query: str,
        topK: int = 3,
        expandRelated: bool = True,
    ) -> list[ResolveHit]:
        """按别名/标题子串与词重叠打分，返回 TopK；可选展开 related。"""
        q = (query or "").strip().lower()
        if not q:
            return []

        scored: list[ResolveHit] = []
        for module in self._modules:
            score, reason = self._Score(module, q)
            if score > 0:
                scored.append(ResolveHit(module=module, score=score, reason=reason))

        scored.sort(key=lambda h: (-h.score, h.module.id))
        primary = scored[: max(1, topK)]

        if not expandRelated:
            return primary

        return self._ExpandRelated(primary)

    def GetById(self, moduleId: str) -> ModuleSpec | None:
        return self._byId.get(moduleId.strip().lower())

    def CollectRoots(
        self,
        hits: list[ResolveHit],
        resolvePath: Callable[[str], str],
        existingOnly: bool = False,
    ) -> list[str]:
        """汇总命中模块的绝对 roots（去重）。"""
        seen: set[str] = set()
        roots: list[str] = []
        for hit in hits:
            for root in hit.module.roots:
                absRoot = resolvePath(root)
                key = os.path.normcase(os.path.normpath(absRoot))
                if key in seen:
                    continue
                if existingOnly and not os.path.exists(absRoot):
                    continue
                seen.add(key)
                roots.append(absRoot)
        return roots

    def _Score(self, module: ModuleSpec, query: str) -> tuple[float, str]:
        best = 0.0
        reason = ""
        for token in module.MatchTokens():
            if not token:
                continue
            if query == token:
                return 100.0, f"exact:{token}"
            if token in query:
                score = 50.0 + min(len(token), 40)
                if score > best:
                    best = score
                    reason = f"alias_in_query:{token}"
            elif query in token and len(query) >= 2:
                score = 20.0 + len(query)
                if score > best:
                    best = score
                    reason = f"query_in_alias:{token}"

        # 分词粗匹配（空格/标点）
        parts = _SplitQuery(query)
        overlap = 0
        hitTokens: list[str] = []
        moduleTokens = set(module.MatchTokens())
        for part in parts:
            if len(part) < 2:
                continue
            for token in moduleTokens:
                if part in token or token in part:
                    overlap += 1
                    hitTokens.append(token)
                    break
        if overlap:
            score = 10.0 * overlap
            if score > best:
                best = score
                reason = f"token_overlap:{','.join(hitTokens[:3])}"

        return best, reason

    def _ExpandRelated(self, primary: list[ResolveHit]) -> list[ResolveHit]:
        result = list(primary)
        seen = {h.module.id.lower() for h in primary}
        for hit in primary:
            for relatedId in hit.module.related:
                key = relatedId.lower()
                if key in seen:
                    continue
                module = self._byId.get(key)
                if module is None:
                    continue
                seen.add(key)
                result.append(
                    ResolveHit(
                        module=module,
                        score=hit.score * 0.5,
                        reason=f"related_of:{hit.module.id}",
                    )
                )
        return result


def _SplitQuery(query: str) -> list[str]:
    buf: list[str] = []
    cur: list[str] = []
    for ch in query:
        if ch.isalnum() or ch in ("_", "-"):
            cur.append(ch)
        else:
            if cur:
                buf.append("".join(cur).lower())
                cur = []
    if cur:
        buf.append("".join(cur).lower())
    # 中文无空格：也按连续 CJK 切不动，整句已在 alias 子串里覆盖
    return buf
