"""Wiki 健康检查：审计知识库质量，发现问题。

检查项目:
  1. 矛盾检测 — 跨文章发现不一致陈述
  2. 孤立概念 — 没有 [[wiki-links]] 的文章
  3. 瘦文章 — 内容过短的概念
  4. 断链检测 — 引用不存在概念的文章
  5. 过时概念 — 长时间未更新的概念
  6. 缺失来源 — 未关联 raw/ 文件的文章

Usage:
  python scripts/health_check.py <kb_root> [--model <name>] [--config <path>]
  python scripts/health_check.py <kb_root> --deep  # 深度检查（使用 LLM）
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class HealthChecker:
    """Wiki 健康检查器。"""

    def __init__(self, kbRoot: str, configPath: str = "", modelName: str = ""):
        self._kbRoot = os.path.abspath(kbRoot)
        self._conceptsDir = os.path.join(self._kbRoot, "wiki", "concepts")
        self._indexPath = os.path.join(self._kbRoot, "wiki", "INDEX.md")
        self._statePath = os.path.join(self._kbRoot, "_meta", "compile_state.json")

        self._issues = {
            "contradictions": [],
            "orphans": [],
            "thinArticles": [],
            "brokenLinks": [],
            "staleConcepts": [],
            "missingSources": [],
        }

        self._allConcepts: dict[str, str] = {}  # name → content
        self._configPath = configPath
        self._modelName = modelName

    def _LoadAllConcepts(self) -> dict[str, str]:
        """加载所有概念文章。"""
        concepts = {}
        if not os.path.exists(self._conceptsDir):
            return concepts
        for f in os.listdir(self._conceptsDir):
            if f.endswith(".md"):
                name = f[:-3]
                with open(os.path.join(self._conceptsDir, f), "r", encoding="utf-8") as fh:
                    concepts[name] = fh.read()
        return concepts

    def CheckOrphans(self) -> list[str]:
        """检查孤立概念（没有被其他概念引用的文章）。"""
        if not self._allConcepts:
            self._allConcepts = self._LoadAllConcepts()

        referenced = set()
        for name, content in self._allConcepts.items():
            # 提取所有 [[wikilinks]]
            links = re.findall(r"\[\[([^\]]+)\]\]", content)
            for link in links:
                referenced.add(link)

        orphans = [name for name in self._allConcepts if name not in referenced]
        self._issues["orphans"] = orphans
        return orphans

    def CheckThinArticles(self, minChars: int = 200) -> list[tuple[str, int]]:
        """检查内容过短的文章。"""
        if not self._allConcepts:
            self._allConcepts = self._LoadAllConcepts()

        thin = []
        for name, content in self._allConcepts.items():
            # 去除 frontmatter 后计算正文长度
            body = re.sub(r"^---[\s\S]*?---\n*", "", content)
            charCount = len(body.strip())
            if charCount < minChars:
                thin.append((name, charCount))
        thin.sort(key=lambda x: x[1])
        self._issues["thinArticles"] = thin
        return thin

    def CheckBrokenLinks(self) -> list[tuple[str, list[str]]]:
        """检查断链（引用不存在概念的文章）。"""
        if not self._allConcepts:
            self._allConcepts = self._LoadAllConcepts()

        broken = []
        allNames = set(self._allConcepts.keys())

        for name, content in self._allConcepts.items():
            links = re.findall(r"\[\[([^\]]+)\]\]", content)
            brokenLinks = [link for link in links if link not in allNames]
            if brokenLinks:
                broken.append((name, brokenLinks))
        self._issues["brokenLinks"] = broken
        return broken

    def CheckMissingSources(self) -> list[str]:
        """检查 frontmatter 中缺少 sources 字段的概念。"""
        if not self._allConcepts:
            self._allConcepts = self._LoadAllConcepts()

        missing = []
        for name, content in self._allConcepts.items():
            # 提取 frontmatter 中的 sources
            fmMatch = re.match(r"^---\n([\s\S]*?)\n---", content)
            if not fmMatch:
                missing.append(name)
                continue
            fm = fmMatch.group(1)
            if "sources:" not in fm:
                missing.append(name)
        self._issues["missingSources"] = missing
        return missing

    def CheckStaleConcepts(self, maxDays: int = 30) -> list[tuple[str, str]]:
        """检查过时概念（超过 maxDays 天未更新）。"""
        if not self._allConcepts:
            self._allConcepts = self._LoadAllConcepts()

        stale = []
        cutoff = datetime.now() - timedelta(days=maxDays)

        for name, content in self._allConcepts.items():
            fmMatch = re.match(r"^---\n([\s\S]*?)\n---", content)
            if not fmMatch:
                continue
            fm = fmMatch.group(1)
            dateMatch = re.search(r"last_compiled:\s*(\d{4}-\d{2}-\d{2})", fm)
            if dateMatch:
                try:
                    compiledDate = datetime.strptime(dateMatch.group(1), "%Y-%m-%d")
                    if compiledDate < cutoff:
                        stale.append((name, dateMatch.group(1)))
                except ValueError:
                    pass
        stale.sort(key=lambda x: x[1])
        self._issues["staleConcepts"] = stale
        return stale

    def DeepCheck(self) -> list[dict]:
        """使用 LLM 深度检查矛盾和不一致。"""
        if not self._configPath:
            print("  [!] 未配置 LLM，跳过深度检查")
            return []

        if not self._allConcepts:
            self._allConcepts = self._LoadAllConcepts()

        if len(self._allConcepts) < 2:
            print("  [!] 概念不足，跳过深度检查")
            return []

        from llm import LLMManager

        manager = LLMManager(self._configPath)
        modelName = self._modelName or manager.DefaultModel

        # 构建检查请求
        conceptsSummary = "\n\n".join(
            f"## {name}\n{content[:500]}..."
            for name, content in list(self._allConcepts.items())[:15]
        )

        prompt = f"""你是一个知识库审计员。请检查以下知识库概念之间是否存在矛盾或不一致：

{conceptsSummary}

请以 JSON 格式输出所有发现的问题：

```json
{{
  "contradictions": [
    {{
      "concept1": "概念A",
      "statement1": "陈述1",
      "concept2": "概念B",
      "statement2": "陈述2",
      "severity": "high/medium/low",
      "suggestion": "修复建议"
    }}
  ],
  "gaps": ["发现的知识缺口"],
  "suggestions": ["改进建议"]
}}
```

如果没有发现问题，返回空的 contradictions 数组。"""

        messages = [
            {"role": "system", "content": "你是知识库质量审计员。仔细检查概念间的一致性。"},
            {"role": "user", "content": prompt},
        ]

        print(f"  -> 调用 {modelName} 进行深度检查...")
        try:
            client = manager.GetClient(modelName)
            resp = client.Invoke(messages, temperature=0.2)
        except Exception as e:
            print(f"  [FAIL] LLM 调用失败: {e}")
            manager.Close()
            return []

        manager.Close()

        # 解析 JSON
        try:
            jsonMatch = re.search(r"```(?:json)?\s*([\s\S]*?)```", resp.content)
            if jsonMatch:
                result = json.loads(jsonMatch.group(1))
            else:
                result = json.loads(resp.content)
        except json.JSONDecodeError:
            print(f"  [!] 无法解析 LLM 输出")
            return []

        contradictions = result.get("contradictions", [])
        self._issues["contradictions"] = contradictions
        return contradictions

    def Run(self, deep: bool = False) -> dict:
        """运行所有健康检查。"""
        print("\n" + "=" * 60)
        print("Wiki 健康检查")
        print(f"知识库: {self._kbRoot}")
        print("=" * 60)

        # 基础检查
        print("\n--- 基础检查 ---")

        orphans = self.CheckOrphans()
        print(f"  孤立概念 (未被引用): {len(orphans)}")
        for o in orphans:
            print(f"    ⚠ {o}")

        thin = self.CheckThinArticles()
        print(f"  瘦文章 (<200字符): {len(thin)}")
        for name, count in thin:
            print(f"    ⚠ {name} ({count} 字符)")

        broken = self.CheckBrokenLinks()
        print(f"  断链 (引用不存在概念): {len(broken)}")
        for name, links in broken:
            print(f"    ⚠ {name} → [{', '.join(links)}]")

        missingSources = self.CheckMissingSources()
        print(f"  缺失来源: {len(missingSources)}")
        for name in missingSources:
            print(f"    ⚠ {name}")

        stale = self.CheckStaleConcepts()
        print(f"  过时概念 (>30天未更新): {len(stale)}")
        for name, date in stale:
            print(f"    ⚠ {name} (最后编译: {date})")

        # 深度检查
        if deep:
            print("\n--- 深度检查 (LLM) ---")
            contradictions = self.DeepCheck()
            print(f"  矛盾/不一致: {len(contradictions)}")
            for c in contradictions:
                print(f"    ⚠ [{c.get('severity', '?')}] {c.get('concept1', '?')} vs {c.get('concept2', '?')}")
                print(f"       {c.get('statement1', '')[:60]}...")
                print(f"       → {c.get('suggestion', '')[:80]}")

        # 汇总
        print(f"\n{'='*60}")
        total = (
            len(orphans)
            + len(thin)
            + len(broken)
            + len(missingSources)
            + len(stale)
            + len(self._issues["contradictions"])
        )
        if total == 0:
            print("✅ 知识库状态良好，未发现问题")
        else:
            print(f"⚠ 共发现 {total} 个问题:")
            print(f"   孤立概念: {len(orphans)}")
            print(f"   瘦文章: {len(thin)}")
            print(f"   断链: {len(broken)}")
            print(f"   缺失来源: {len(missingSources)}")
            print(f"   过时概念: {len(stale)}")
            print(f"   矛盾/不一致: {len(self._issues['contradictions'])}")

        return self._issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Wiki 知识库健康检查")
    parser.add_argument("kbRoot", help="知识库根目录路径")
    parser.add_argument("--config", default="worksapce/models.json", help="LLM 配置文件路径")
    parser.add_argument("--model", default="", help="指定模型")
    parser.add_argument("--deep", action="store_true", help="使用 LLM 进行深度矛盾检查")
    args = parser.parse_args()

    kbRoot = os.path.abspath(args.kbRoot)
    configPath = os.path.join(_PROJECT_ROOT, args.config)
    if not os.path.exists(configPath):
        configPath = args.config

    checker = HealthChecker(kbRoot, configPath, args.model)
    checker.Run(deep=args.deep)


if __name__ == "__main__":
    main()
