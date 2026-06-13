"""查询 Wiki 知识库：读取 wiki/ 中的概念文章，结合 LLM 综合回答。

Usage:
  python scripts/query.py <kb_root> "你的问题" [--model <name>] [--config <path>]
  python scripts/query.py <kb_root> --interactive  # 交互式查询模式

工作方式:
  1. 将用户问题与 wiki/INDEX.md 一起发给 LLM，让 LLM 判断需要哪些概念
  2. 读取相关概念文章的完整内容
  3. 将概念内容作为上下文，让 LLM 综合回答
"""

import argparse
import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from llm import LLMManager

# ==================== 查询提示词 ====================

CONCEPT_SELECTION_PROMPT = """你是一个知识库查询助手。以下是知识库的概念索引：

{index}

用户的问题是："{query}"

请列出回答这个问题需要参考的概念（从上述索引中选择）。只输出概念名称，每行一个，不要输出其他内容。

示例输出：
概念A
概念B
"""

ANSWER_PROMPT = """你是一个知识库查询助手。以下是知识库中相关概念的内容：

{context}

请基于以上知识库内容回答用户的问题。如果知识库中的信息不足以完整回答，请明确说明哪些信息缺失。

用户问题: {query}
"""

INTERACTIVE_ANSWER_PROMPT = """你是一个知识库查询助手。以下是知识库中相关概念的内容：

{context}

请基于以上知识库内容回答用户的问题。回答要求：
1. 优先使用知识库中的信息
2. 如果信息不完整，明确说明缺失部分
3. 使用 [[概念名]] 语法引用知识库中的其他概念
4. 如果有多个来源存在矛盾，指出矛盾所在
"""


class WikiQuerier:
    """Wiki 知识库查询器。"""

    def __init__(self, kbRoot: str, configPath: str, modelName: str = ""):
        self._kbRoot = os.path.abspath(kbRoot)
        self._conceptsDir = os.path.join(self._kbRoot, "wiki", "concepts")
        self._indexPath = os.path.join(self._kbRoot, "wiki", "INDEX.md")

        self._manager = LLMManager(configPath)
        self._modelName = modelName or self._manager.DefaultModel

    def _ReadIndex(self) -> str:
        """读取概念索引。"""
        if os.path.exists(self._indexPath):
            with open(self._indexPath, "r", encoding="utf-8") as f:
                return f.read()
        return "（索引为空）"

    def _ReadConcept(self, name: str) -> str:
        """读取指定概念的文章内容。"""
        safeName = name.replace("/", "_").replace("\\", "_")
        path = os.path.join(self._conceptsDir, f"{safeName}.md")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            # 截断过长内容
            if len(content) > 3000:
                content = content[:3000] + "\n\n... (内容已截断)"
            return content
        return f"[概念 '{name}' 的文章不存在]"

    def _SelectConcepts(self, query: str) -> list[str]:
        """让 LLM 根据问题选择相关概念。"""
        index = self._ReadIndex()
        prompt = CONCEPT_SELECTION_PROMPT.format(index=index, query=query)

        messages = [
            {"role": "system", "content": "你是一个精准的概念选择器。只输出概念名称，每行一个。"},
            {"role": "user", "content": prompt},
        ]

        try:
            client = self._manager.GetClient(self._modelName)
            resp = client.Invoke(messages, temperature=0.1)
        except Exception as e:
            print(f"  [FAIL] 概念选择失败: {e}")
            return []

        concepts = []
        for line in resp.content.strip().split("\n"):
            line = line.strip().strip("- ").strip("* ")
            if line and not line.startswith("#") and not line.startswith("```"):
                # 清理可能的前缀
                concepts.append(line)

        return concepts[:8]  # 限制最多 8 个概念

    def Query(self, query: str) -> str:
        """执行查询。

        Returns:
            LLM 综合回答。
        """
        print(f"\n查询: {query}\n")

        # 第一步：选择相关概念
        print("-> 分析问题，选择相关概念...")
        selectedConcepts = self._SelectConcepts(query)
        if not selectedConcepts:
            # 如果没有选出概念，使用索引全文作为上下文
            context = self._ReadIndex()
            print("  (使用完整索引作为上下文)")
        else:
            print(f"  选中概念: {', '.join(selectedConcepts)}")
            # 第二步：读取概念内容
            contextParts = []
            for name in selectedConcepts:
                content = self._ReadConcept(name)
                contextParts.append(f"## {name}\n\n{content}")
            context = "\n\n---\n\n".join(contextParts)

        # 第三步：综合回答
        print(f"-> 调用 {self._modelName} 综合回答...")
        prompt = ANSWER_PROMPT.format(context=context, query=query)
        messages = [
            {"role": "system", "content": "你是知识库查询助手。基于知识库内容精准回答，不编造信息。"},
            {"role": "user", "content": prompt},
        ]

        try:
            client = self._manager.GetClient(self._modelName)
            resp = client.Invoke(messages, temperature=0.5)
        except Exception as e:
            return f"查询失败: {e}"

        return resp.content

    def Interactive(self) -> None:
        """交互式查询模式。"""
        print("\n" + "=" * 60)
        print("Wiki 知识库交互查询")
        print(f"知识库: {self._kbRoot}")
        print(f"模型: {self._modelName}")
        print("输入 'quit' 或 'exit' 退出, 'concepts' 查看所有概念")
        print("=" * 60 + "\n")

        while True:
            try:
                query = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见!")
                break

            if not query:
                continue
            if query.lower() in ("quit", "exit", "q"):
                print("再见!")
                break
            if query.lower() == "concepts":
                index = self._ReadIndex()
                print(index)
                continue
            if query.lower() == "help":
                print("命令:")
                print("  concepts  - 查看所有概念")
                print("  quit/exit - 退出")
                print("  其他输入   - 查询知识库")
                continue

            answer = self.Query(query)
            print(f"\n📖 回答:\n{answer}\n")
            print("-" * 60)

    def Close(self) -> None:
        self._manager.Close()


def main() -> None:
    parser = argparse.ArgumentParser(description="查询 Wiki 知识库")
    parser.add_argument("kbRoot", help="知识库根目录路径")
    parser.add_argument("query", nargs="?", default="", help="查询问题")
    parser.add_argument("--config", default="worksapce/models.json", help="LLM 配置文件路径")
    parser.add_argument("--model", default="", help="指定模型")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互式查询模式")
    args = parser.parse_args()

    kbRoot = os.path.abspath(args.kbRoot)
    configPath = os.path.join(_PROJECT_ROOT, args.config)
    if not os.path.exists(configPath):
        configPath = args.config

    querier = WikiQuerier(kbRoot, configPath, args.model)
    try:
        if args.interactive or not args.query:
            querier.Interactive()
        else:
            answer = querier.Query(args.query)
            print(f"\n📖 回答:\n{answer}")
    finally:
        querier.Close()


if __name__ == "__main__":
    main()
