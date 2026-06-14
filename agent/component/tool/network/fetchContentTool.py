"""网页抓取工具 —— 获取网页文本内容。"""

from __future__ import annotations

import re
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import urlparse

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent

MAX_CONTENT_LENGTH = 100000
TIMEOUT_SECONDS = 30


@ToolComponent.Register
class FetchContentTool(BaseTool):
    """抓取指定 URL 的网页内容。

    返回纯文本内容，自动移除 HTML 标签。
    """

    name: str = "fetch_content"
    description: str = (
        "Fetch the text content from a web page URL. "
        "Returns the page content as plain text with HTML tags stripped. "
        "Use this to read documentation, articles, or any web content."
    )
    category: EToolCategory = EToolCategory.NETWORK
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The HTTP or HTTPS URL to fetch content from",
            },
        },
        "required": ["url"],
    }

    def _Invoke(self, url: str) -> ToolResult:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return ToolResult.Fail(f"Unsupported URL scheme: {parsed.scheme}", toolName=self.name)

            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AgentTool/1.0)"})
            with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                contentType = resp.headers.get("Content-Type", "")
                raw = resp.read(MAX_CONTENT_LENGTH + 1)
                truncated = len(raw) > MAX_CONTENT_LENGTH

            # 尝试解码
            for encoding in ("utf-8", "latin-1"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = raw.decode("utf-8", errors="replace")

            # 如果是 HTML，简单去除标签
            if "text/html" in contentType.lower() or "<html" in text[:500].lower():
                text = self._StripHtml(text)

            if truncated:
                text = text[:MAX_CONTENT_LENGTH] + "\n\n... (content truncated)"

            header = f"[Fetched from: {url}]\n"
            return ToolResult.Ok(header + text, toolName=self.name)

        except URLError as exc:
            return ToolResult.Fail(f"Failed to fetch URL: {exc}", toolName=self.name)
        except Exception as exc:
            return ToolResult.Fail(f"Fetch failed: {exc}", toolName=self.name)

    @staticmethod
    def _StripHtml(html: str) -> str:
        """移除 HTML 标签，提取纯文本。"""
        # 移除 script 和 style 块
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # 移除 HTML 标签
        text = re.sub(r"<[^>]+>", " ", html)
        # 解码常见 HTML 实体
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        # 合并空白
        text = re.sub(r"\s+", " ", text)
        # 在块级标签后添加换行
        text = re.sub(r"\s*(<br\s*/?>|</p>|</div>|</h[1-6]>|</li>)\s*", "\n", text, flags=re.IGNORECASE)
        return text.strip()
