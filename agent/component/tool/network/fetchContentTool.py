"""网页抓取工具 —— 获取网页文本内容。"""

from __future__ import annotations

import ipaddress
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent

MAX_CONTENT_LENGTH = 100000
TIMEOUT_SECONDS = 30
MAX_REDIRECTS = 5


@ToolComponent.Register
class FetchContentTool(BaseTool):
    """抓取指定 URL 的网页内容。

    返回纯文本内容，自动移除 HTML 标签。
    内置 SSRF 防护：拒绝指向 localhost / 内网 / 回环 / 链路本地地址的 URL。
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
                return ToolResult.Fail(
                    f"Unsupported URL scheme: {parsed.scheme}", toolName=self.name
                )

            # ---- SSRF 防护：拒绝内网 / 回环 / 链路本地地址 ----
            if self._IsInternalUrl(url):
                return ToolResult.Fail(
                    f"SSRF blocked: URL points to internal/loopback address: {url}",
                    toolName=self.name,
                )

            # ---- 手动跟随重定向，限制最大次数 ----
            raw, contentType, finalUrl = self._FetchWithRedirects(url)

            truncated = len(raw) > MAX_CONTENT_LENGTH
            raw = raw[: MAX_CONTENT_LENGTH + 1]

            # 尝试解码
            text = ""
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

            header = f"[Fetched from: {finalUrl}]\n"
            return ToolResult.Ok(header + text, toolName=self.name)

        except URLError as exc:
            return ToolResult.Fail(f"Failed to fetch URL: {exc}", toolName=self.name)
        except ValueError as exc:
            return ToolResult.Fail(str(exc), toolName=self.name)
        except Exception as exc:
            return ToolResult.Fail(f"Fetch failed: {exc}", toolName=self.name)

    def _IsInternalUrl(self, url: str) -> bool:
        """检测 URL 是否指向内网 / 回环 / 链路本地地址。

        Returns:
            True 表示内网地址（应拒绝）；False 表示外网域名或 IP（允许）。
        """
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return True
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return True
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            # 域名而非 IP，允许通过（DNS 解析后的二次校验在生产环境另外处理）
            return False

    def _FetchWithRedirects(self, url: str) -> tuple[bytes, str, str]:
        """禁用 urllib 自动重定向，手动跟随并对每跳进行 SSRF 校验。

        Returns:
            (rawBytes, contentType, finalUrl)
        """
        # 自定义 opener：拒绝自动重定向，便于手动控制次数
        class _NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401,N802
                return None  # 阻止自动跟随

        opener = build_opener(_NoRedirect())

        currentUrl = url
        for hop in range(MAX_REDIRECTS + 1):
            req = Request(
                currentUrl,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AgentTool/1.0)"},
            )
            try:
                resp = opener.open(req, timeout=TIMEOUT_SECONDS)
                contentType = resp.headers.get("Content-Type", "")
                raw = resp.read(MAX_CONTENT_LENGTH + 1)
                resp.close()
                return raw, contentType, currentUrl
            except HTTPError as exc:
                # urllib 在重定向被阻止时抛出 HTTPError(code=3xx)
                if 300 <= exc.code < 400:
                    location = exc.headers.get("Location") if exc.headers else None
                    if not location:
                        raise URLError(f"Redirect without Location header: {exc.code}")
                    nextUrl = urljoin(currentUrl, location)
                    if hop >= MAX_REDIRECTS:
                        raise URLError(
                            f"Too many redirects (>{MAX_REDIRECTS}) starting from {url}"
                        )
                    if self._IsInternalUrl(nextUrl):
                        raise ValueError(
                            f"SSRF blocked on redirect: {nextUrl} resolves to internal address"
                        )
                    currentUrl = nextUrl
                    continue
                raise

        raise URLError(f"Too many redirects (>{MAX_REDIRECTS}) starting from {url}")

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
