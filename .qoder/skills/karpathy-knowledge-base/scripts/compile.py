"""LLM 编译脚本：读取 raw/ 中的源文档，调用 LLM 编译为 wiki/ 中的结构化知识。

编译流程:
  1. 扫描 raw/ 目录，找出未编译或已变更的文件
  2. 对每个文件调用 LLM 提取概念、事实、关系
  3. 在 wiki/concepts/ 下创建/更新概念文章
  4. 更新 wiki/INDEX.md
  5. 更新 _meta/compile_state.json

Usage:
  python scripts/compile.py <kb_root> [--model <name>] [--config <path>] [--force]
  python scripts/compile.py <kb_root> --dry-run   # 预览将要编译的文件

依赖:
  需要项目 llm/ 模块和 worksapce/models.json 配置
"""

import argparse
import json
import os
import sys
from datetime import datetime

# 将项目根加入 sys.path，确保能 import llm
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from llm import LLMManager

# ==================== 编译提示词 ====================

COMPILE_SYSTEM_PROMPT = """你是一个 Wiki 编译器。你的任务是将原始文档编译成结构化的知识库 Wiki。

请仔细阅读提供的源文档，然后执行以下任务：

## 输出格式

你必须严格按照以下 JSON 格式输出，不要输出任何其他内容：

```json
{
  "concepts": [
    {
      "title": "概念名称",
      "summary": "一句话摘要（不超过50字）",
      "content": "详细的 Wiki 文章内容（Markdown 格式，包含 [[wiki-links]] 链接到其他概念）",
      "category": "分类（如: 方法论/工具/理论/实践/其他）",
      "related": ["关联概念1", "关联概念2"],
      "confidence": "high/medium/low",
      "keyFacts": ["事实1", "事实2"]
    }
  ],
  "crossReferences": {
    "概念A": ["概念B", "概念C"],
    "概念B": ["概念A"]
  },
  "newTopics": ["建议新增的概念"],
  "contradictions": [
    {
      "statement1": "陈述1",
      "source1": "来源文件1",
      "statement2": "陈述2",
      "source2": "来源文件2",
      "resolution": "可能的解释或建议"
    }
  ]
}
```

## 规则

1. 每个概念提取 atomic facts（原子事实），粒度适中
2. 使用 `[[概念名]]` 的 wiki-link 语法关联概念
3. 如果新建的概念与已有概念重名，请在 content 中合并信息
4. confidence 评估: high=源文档明确陈述, medium=合理推断, low=仅有暗示
5. 遇到矛盾时列在 contradictions 中
6. 如果源文档引用了新的重要概念但信息不足，列在 newTopics 中建议后续补充
"""

CONCEPT_EXIST_PROMPT = """你是一个 Wiki 编译器。请阅读以下新的源文档内容，并更新已有的概念文章。

## 已有概念

已有概念列表: {existing_concepts}

## 已有概念当前内容

{existing_content}

## 任务

将新源文档中的信息合并到已有概念中。如果新文档引入了新的概念，请一并创建。

严格按照以下 JSON 格式输出：

```json
{{
  "concepts": [
    {{
      "title": "概念名称（必须匹配已有概念名或使用新名称）",
      "action": "update/create",
      "summary": "更新后的一句话摘要",
      "content": "合并后的完整 Wiki 文章内容（Markdown，含 [[wiki-links]]）",
      "category": "分类",
      "related": ["关联概念"],
      "confidence": "high/medium/low",
      "keyFacts": ["更新后的事实列表"]
    }}
  ],
  "crossReferences": {{}},
  "newTopics": [],
  "contradictions": []
}}
```
"""

INCREMENTAL_COMPILE_PROMPT = """你是一个 Wiki 编译器。当前 Wiki 已有以下概念：

{existing_concepts}

请阅读以下新的源文档，判断需要：
1. 更新哪些已有概念（如果新文档包含相关信息）
2. 创建哪些新概念
3. 建立哪些新的交叉引用

对于每篇源文档，请识别其核心论点和关键概念。

严格按照 JSON 格式输出（同通用编译格式）。
"""


# ==================== 编译引擎 ====================

class WikiCompiler:
    """LLM Wiki 编译器。"""

    def __init__(self, kbRoot: str, configPath: str, modelName: str = ""):
        self._kbRoot = os.path.abspath(kbRoot)
        self._rawDir = os.path.join(self._kbRoot, "raw")
        self._wikiDir = os.path.join(self._kbRoot, "wiki")
        self._conceptsDir = os.path.join(self._wikiDir, "concepts")
        self._statePath = os.path.join(self._kbRoot, "_meta", "compile_state.json")
        self._indexPath = os.path.join(self._wikiDir, "INDEX.md")

        self._manager = LLMManager(configPath)
        self._modelName = modelName or self._manager.DefaultModel

        self._state = self._LoadState()

    def _LoadState(self) -> dict:
        if os.path.exists(self._statePath):
            with open(self._statePath, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"processedFiles": {}, "compileLog": [], "totalConcepts": 0}

    def _SaveState(self) -> None:
        self._state["lastCompiled"] = datetime.now().isoformat()
        with open(self._statePath, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    def _HashFile(self, filePath: str) -> str:
        import hashlib
        h = hashlib.md5()
        with open(filePath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _ListExistingConcepts(self) -> list[str]:
        """列出 wiki/concepts/ 下已有的概念名称。"""
        if not os.path.exists(self._conceptsDir):
            return []
        concepts = []
        for f in os.listdir(self._conceptsDir):
            if f.endswith(".md"):
                concepts.append(f[:-3])  # 去掉 .md
        return concepts

    def _ReadConceptContent(self, conceptName: str) -> str:
        """读取已有概念的文章内容。"""
        path = os.path.join(self._conceptsDir, f"{conceptName}.md")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def _FindUnprocessedFiles(self) -> list[str]:
        """找出 raw/ 中未编译或已变更的文件。"""
        unprocessed = []
        processed = self._state.get("processedFiles", {})

        if not os.path.exists(self._rawDir):
            return []

        for f in sorted(os.listdir(self._rawDir)):
            if f.startswith("."):
                continue
            fullPath = os.path.join(self._rawDir, f)
            if not os.path.isfile(fullPath):
                continue

            relPath = f"raw/{f}"
            currentHash = self._HashFile(fullPath)

            if relPath not in processed:
                unprocessed.append(fullPath)
            elif not processed[relPath].get("compiled", True):
                unprocessed.append(fullPath)
            elif processed[relPath].get("hash") != currentHash:
                unprocessed.append(fullPath)

        return unprocessed

    def _ReadFileContent(self, filePath: str) -> str:
        """读取文件内容，支持 .md 和 .txt。"""
        try:
            with open(filePath, "r", encoding="utf-8") as f:
                content = f.read()
            # 截断过长的内容（保留前 8000 字符）
            if len(content) > 8000:
                content = content[:8000] + "\n\n... (内容已截断)"
            return content
        except UnicodeDecodeError:
            return f"[二进制文件，无法直接读取: {os.path.basename(filePath)}]"

    def _CallLLM(self, systemPrompt: str, userContent: str) -> dict:
        """调用 LLM 并解析 JSON 响应。"""
        messages = [
            {"role": "system", "content": systemPrompt},
            {"role": "user", "content": userContent},
        ]

        print(f"  -> 调用 {self._modelName} ...")
        try:
            client = self._manager.GetClient(self._modelName)
            resp = client.Invoke(messages, temperature=0.3, maxTokens=16384)
        except Exception as e:
            print(f"  [FAIL] LLM 调用失败: {e}")
            return {"concepts": [], "crossReferences": {}, "newTopics": [], "contradictions": []}

        content = resp.content

        # 尝试从 markdown 代码块中提取 JSON
        import re
        jsonMatch = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if jsonMatch:
            content = jsonMatch.group(1).strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # 尝试修复常见问题
            print(f"  [!] JSON 解析失败，尝试修复...")
            content = content.strip()
            if content.endswith(","):
                content = content[:-1]
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                print(f"  [FAIL] 无法解析 LLM 输出，原始内容前200字符: {content[:200]}")
                return {"concepts": [], "crossReferences": {}, "newTopics": [], "contradictions": []}

    def _WriteConceptArticle(self, concept: dict) -> str:
        """将概念写入 wiki/concepts/<name>.md。"""
        os.makedirs(self._conceptsDir, exist_ok=True)

        fileName = concept["title"].replace("/", "_").replace("\\", "_")
        filePath = os.path.join(self._conceptsDir, f"{fileName}.md")

        # 构建 frontmatter + 内容
        frontmatter = f"""---
title: {concept['title']}
category: {concept.get('category', '未分类')}
related: [{', '.join(concept.get('related', []))}]
confidence: {concept.get('confidence', 'medium')}
last_compiled: {datetime.now().strftime('%Y-%m-%d')}
---

# {concept['title']}

> {concept.get('summary', '')}

{concept.get('content', '')}

## 关键事实

"""
        for fact in concept.get("keyFacts", []):
            frontmatter += f"- {fact}\n"

        with open(filePath, "w", encoding="utf-8") as f:
            f.write(frontmatter)

        return filePath

    def _UpdateIndex(self, concepts: list[dict]) -> None:
        """更新 wiki/INDEX.md。"""
        existing = self._ListExistingConcepts()
        allConcepts = sorted(set(existing))

        lines = []
        lines.append(f"# {self._state.get('kbName', 'Knowledge Base')}\n")
        lines.append(f"最后编译: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append(f"概念总数: {len(allConcepts)}\n\n")
        lines.append("## 概念索引\n\n")
        lines.append("| 概念 | 摘要 | 分类 | 置信度 |\n")
        lines.append("|------|------|------|--------|\n")

        for name in allConcepts:
            # 从新编译的概念中获取信息
            summary = ""
            category = ""
            confidence = ""
            for c in concepts:
                if c.get("title") == name:
                    summary = c.get("summary", "")
                    category = c.get("category", "")
                    confidence = c.get("confidence", "")
                    break

            # 尝试从已有文件中读取 frontmatter
            if not summary:
                conceptPath = os.path.join(self._conceptsDir, f"{name}.md")
                if os.path.exists(conceptPath):
                    with open(conceptPath, "r", encoding="utf-8") as f:
                        firstLines = "".join(f.readline() for _ in range(15))
                    import re
                    sMatch = re.search(r"> (.+)", firstLines)
                    if sMatch:
                        summary = sMatch.group(1)

            lines.append(f"| [[{name}]] | {summary[:40]} | {category} | {confidence} |\n")

        os.makedirs(os.path.dirname(self._indexPath), exist_ok=True)
        with open(self._indexPath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def Compile(self, force: bool = False, dryRun: bool = False) -> dict:
        """执行编译。

        Args:
            force: 是否强制重新编译所有文件
            dryRun: 是否只预览不实际编译

        Returns:
            编译统计信息。
        """
        if force:
            files = [
                os.path.join(self._rawDir, f)
                for f in sorted(os.listdir(self._rawDir))
                if not f.startswith(".") and os.path.isfile(os.path.join(self._rawDir, f))
            ]
        else:
            files = self._FindUnprocessedFiles()

        if not files:
            print("没有需要编译的文件（所有文件已是最新）")
            return {"compiled": 0, "concepts": 0, "files": 0}

        print(f"\n{'[DRY RUN] ' if dryRun else ''}发现 {len(files)} 个待编译文件:")
        for f in files:
            print(f"  - {os.path.basename(f)}")

        if dryRun:
            return {"compiled": 0, "concepts": 0, "files": len(files)}

        existingConcepts = self._ListExistingConcepts()
        allNewConcepts = []
        compiledCount = 0

        for filePath in files:
            fileName = os.path.basename(filePath)
            print(f"\n{'='*60}")
            print(f"编译: {fileName}")
            print(f"{'='*60}")

            content = self._ReadFileContent(filePath)
            if content.startswith("[二进制文件"):
                print(f"  [!] 跳过二进制文件")
                
                continue

            # 构建用户提示词
            if existingConcepts:
                # 增量编译模式
                userPrompt = f"""## 源文档: {fileName}

{content}

## 已有概念

{', '.join(existingConcepts)}

请提取本文档中的新概念，并将相关信息合并到已有概念中。
"""
                systemPrompt = CONCEPT_EXIST_PROMPT.replace(
                    "{existing_concepts}", ", ".join(existingConcepts)
                ).replace(
                    "{existing_content}",
                    "\n\n".join(
                        f"### {c}\n{self._ReadConceptContent(c)[:500]}"
                        for c in existingConcepts[:10]  # 限制上下文长度
                    ),
                )
            else:
                # 首次编译模式
                userPrompt = f"## 源文档: {fileName}\n\n{content}"
                systemPrompt = COMPILE_SYSTEM_PROMPT

            result = self._CallLLM(systemPrompt, userPrompt)
            concepts = result.get("concepts", [])
            contradictions = result.get("contradictions", [])

            print(f"  -> 提取到 {len(concepts)} 个概念")
            

            for concept in concepts:
                title = concept.get("title", "")
                if not title:
                    continue
                action = concept.get("action", "create")
                filePath_written = self._WriteConceptArticle(concept)
                print(f"    [OK] {'更新' if action == 'update' else '创建'}概念: {title}")
                
                allNewConcepts.append(concept)
                if title not in existingConcepts:
                    existingConcepts.append(title)

            if contradictions:
                print(f"  [!] 发现 {len(contradictions)} 处矛盾")
                
                for c in contradictions:
                    print(f"    - {c.get('statement1', '')[:60]} vs {c.get('statement2', '')[:60]}")

            # 更新编译状态
            relPath = f"raw/{fileName}"
            self._state["processedFiles"][relPath] = {
                "compiledAt": datetime.now().isoformat(),
                "hash": self._HashFile(filePath),
                "compiled": True,
                "conceptsExtracted": len(concepts),
            }
            compiledCount += 1

        # 更新索引
        self._UpdateIndex(allNewConcepts)
        print(f"\n  [OK] INDEX.md 已更新")
        

        # 写入矛盾报告
        self._state["totalConcepts"] = len(existingConcepts)
        self._SaveState()

        stats = {
            "compiled": compiledCount,
            "concepts": len(allNewConcepts),
            "files": len(files),
            "totalConcepts": len(existingConcepts),
        }
        print(f"\n{'='*60}")
        print(f"编译完成: {stats['compiled']} 文件 → {stats['concepts']} 个概念")
        print(f"知识库共 {stats['totalConcepts']} 个概念")
        return stats

    def Close(self) -> None:
        self._manager.Close()


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 编译 raw/ → wiki/")
    parser.add_argument("kbRoot", help="知识库根目录路径")
    parser.add_argument("--config", default="worksapce/models.json", help="LLM 配置文件路径")
    parser.add_argument("--model", default="", help="指定模型（默认使用配置文件中的 defaultModel）")
    parser.add_argument("--force", action="store_true", help="强制重新编译所有文件")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际编译")
    args = parser.parse_args()

    kbRoot = os.path.abspath(args.kbRoot)
    configPath = os.path.join(_PROJECT_ROOT, args.config)
    if not os.path.exists(configPath):
        configPath = args.config  # 尝试作为绝对路径

    compiler = WikiCompiler(kbRoot, configPath, args.model)
    try:
        compiler.Compile(force=args.force, dryRun=args.dry_run)
    finally:
        compiler.Close()


if __name__ == "__main__":
    main()
