"""网页搜索工具 —— 通过搜索引擎搜索网页。"""

from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import quote, urlparse

from ...abstractTool import AbstractTool
from ...eToolCategory import EToolCategory
from ...toolResult import ToolResult
from ...toolRegistry import G_ToolRegistry

MAX_RESULTS = 10
TIMEOUT_SECONDS = 15


@G_ToolRegistry.Register
class SearchWebTool(AbstractTool):
    """使用搜索引擎搜索网页内容。

    返回搜索结果标题、URL 和摘要。
    """

    name: str = "search_web"
    description: str = (
        "Search the web for information. "
        "Returns a list of search results with titles, URLs, and snippets. "
        "Use this to find up-to-date information, documentation, or any web content."
    )
    category: EToolCategory = EToolCategory.NETWORK
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query string",
            },
            "maxResults": {
                "type": "integer",
                "description": "Optional. Maximum number of results to return (default 10)",
            },
        },
        "required": ["query"],
    }

    def _invoke(self, query: str, maxResults: int = MAX_RESULTS) -> ToolResult:
        try:
            maxResults = min(maxResults, MAX_RESULTS)

            results = self._SearchDuckDuckGo(query, maxResults)
            if not results:
                return ToolResult.Ok(
                    f"No search results found for: '{query}'",
                    toolName=self.name,
                )

            lines = [f"[Web search results for: '{query}' ({len(results)} results)]\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r['title']}")
                lines.append(f"   URL: {r['url']}")
                lines.append(f"   {r['snippet']}")
                lines.append("")

            return ToolResult.Ok("\n".join(lines), toolName=self.name)

        except Exception as exc:
            return ToolResult.Fail(f"Search failed: {exc}", toolName=self.name)

    @staticmethod
    def _SearchDuckDuckGo(query: str, maxResults: int) -> list[dict]:
        """使用 DuckDuckGo Instant Answer API 搜索。

        返回格式: [{"title": str, "url": str, "snippet": str}, ...]
        """
        results: list[dict] = []

        try:
            # DuckDuckGo Instant Answer API (不要求 API key)
            encoded = quote(query)
            apiUrl = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"

            req = Request(apiUrl, headers={"User-Agent": "Mozilla/5.0 (compatible; AgentTool/1.0)"})
            with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # Abstract (主摘要)
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("AbstractSource", "DuckDuckGo"),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data["AbstractText"],
                })

            # Related Topics
            for topic in data.get("RelatedTopics", []):
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("FirstURL", "").rsplit("/", 1)[-1].replace("_", " "),
                        "url": topic.get("FirstURL", ""),
                        "snippet": re.sub(r"<[^>]+>", "", topic["Text"]),
                    })
                if len(results) >= maxResults:
                    break

        except (URLError, json.JSONDecodeError, OSError):
            # DuckDuckGo API 失败时不报错，返回空列表
            pass

        return results[:maxResults]
