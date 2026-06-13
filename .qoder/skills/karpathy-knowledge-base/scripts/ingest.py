"""数据摄入脚本：将文档复制/下载到知识库的 raw/ 目录。

支持:
  - 复制本地文件 (.md, .txt, .pdf 等)
  - 批量导入目录
  - 从 URL 抓取网页并保存为 .md（需要 markdownify）

Usage:
  python scripts/ingest.py <kb_root> --file <path>      # 导入单个文件
  python scripts/ingest.py <kb_root> --dir <dir>         # 批量导入目录
  python scripts/ingest.py <kb_root> --url <url>         # 从 URL 抓取
  python scripts/ingest.py <kb_root> --text "内容" --title "标题"  # 直接写入文本
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime


def _HashPath(filePath: str) -> str:
    """计算文件 MD5，用于变更检测。"""
    h = hashlib.md5()
    with open(filePath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def IngestFile(kbRoot: str, sourcePath: str) -> str:
    """将源文件复制到 raw/ 目录。

    Returns:
        目标文件路径。
    """
    rawDir = os.path.join(kbRoot, "raw")
    os.makedirs(rawDir, exist_ok=True)

    fileName = os.path.basename(sourcePath)
    destPath = os.path.join(rawDir, fileName)

    # 文件名冲突处理
    base, ext = os.path.splitext(fileName)
    counter = 1
    while os.path.exists(destPath):
        destPath = os.path.join(rawDir, f"{base}_{counter}{ext}")
        counter += 1

    shutil.copy2(sourcePath, destPath)
    print(f"  ✓ 已摄入: {sourcePath} → {destPath}")
    return destPath


def IngestDir(kbRoot: str, sourceDir: str) -> list[str]:
    """批量导入目录下所有文件（递归）。

    Returns:
        目标文件路径列表。
    """
    ingested = []
    for root, _, files in os.walk(sourceDir):
        for f in files:
            if f.startswith("."):
                continue
            fullPath = os.path.join(root, f)
            try:
                dest = IngestFile(kbRoot, fullPath)
                ingested.append(dest)
            except Exception as e:
                print(f"  ✗ 跳过 {fullPath}: {e}")
    print(f"\n共摄入 {len(ingested)} 个文件")
    return ingested


def IngestText(kbRoot: str, title: str, content: str) -> str:
    """将纯文本写入 raw/ 目录的 .md 文件。

    Returns:
        目标文件路径。
    """
    rawDir = os.path.join(kbRoot, "raw")
    os.makedirs(rawDir, exist_ok=True)

    safeTitle = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
    fileName = f"{safeTitle}.md"
    destPath = os.path.join(rawDir, fileName)

    counter = 1
    while os.path.exists(destPath):
        base = os.path.splitext(fileName)[0]
        destPath = os.path.join(rawDir, f"{base}_{counter}.md")
        counter += 1

    fullContent = f"# {title}\n\n创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{content}\n"
    with open(destPath, "w", encoding="utf-8") as f:
        f.write(fullContent)

    print(f"  ✓ 已写入: {destPath}")
    return destPath


def IngestUrl(kbRoot: str, url: str) -> str:
    """从 URL 抓取网页并保存为 .md。

    Returns:
        目标文件路径。
    """
    try:
        import requests
    except ImportError:
        print("错误: 需要安装 requests 库: pip install requests")
        sys.exit(1)

    print(f"  正在抓取: {url}")
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ 抓取失败: {e}")
        sys.exit(1)

    # 尝试提取标题
    import re
    titleMatch = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE)
    title = titleMatch.group(1).strip() if titleMatch else url.rstrip("/").split("/")[-1]

    # 尝试用 markdownify 转换 HTML
    try:
        from markdownify import markdownify as md
        content = md(resp.text, heading_style="ATX")
    except ImportError:
        content = resp.text
        print("  提示: 安装 markdownify 可获得更好的 HTML→Markdown 转换: pip install markdownify")

    return IngestText(kbRoot, title, content)


def UpdateCompileState(kbRoot: str, ingestedPaths: list[str]) -> None:
    """更新编译状态文件，标记新摄入的文件。"""
    statePath = os.path.join(kbRoot, "_meta", "compile_state.json")
    if not os.path.exists(statePath):
        return

    with open(statePath, "r", encoding="utf-8") as f:
        state = json.load(f)

    for p in ingestedPaths:
        relPath = os.path.relpath(p, kbRoot).replace("\\", "/")
        fileHash = _HashPath(p)
        state["processedFiles"][relPath] = {
            "ingestedAt": datetime.now().isoformat(),
            "hash": fileHash,
            "compiled": False,
        }

    with open(statePath, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"  ✓ 编译状态已更新 ({len(ingestedPaths)} 个文件)")


def main() -> None:
    parser = argparse.ArgumentParser(description="摄入文档到知识库 raw/ 目录")
    parser.add_argument("kbRoot", help="知识库根目录路径")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="导入单个文件")
    group.add_argument("--dir", help="批量导入目录")
    group.add_argument("--url", help="从 URL 抓取网页")
    group.add_argument("--text", help="直接写入文本内容")
    parser.add_argument("--title", default="未命名文档", help="--text 模式下的文档标题")
    args = parser.parse_args()

    kbRoot = os.path.abspath(args.kbRoot)
    rawDir = os.path.join(kbRoot, "raw")
    if not os.path.exists(rawDir):
        print(f"错误: 知识库不存在，请先运行 init_kb.py 初始化: {kbRoot}")
        sys.exit(1)

    ingested = []

    if args.file:
        if not os.path.exists(args.file):
            print(f"错误: 文件不存在: {args.file}")
            sys.exit(1)
        dest = IngestFile(kbRoot, args.file)
        ingested.append(dest)
    elif args.dir:
        if not os.path.isdir(args.dir):
            print(f"错误: 目录不存在: {args.dir}")
            sys.exit(1)
        ingested = IngestDir(kbRoot, args.dir)
    elif args.url:
        dest = IngestUrl(kbRoot, args.url)
        ingested.append(dest)
    elif args.text:
        dest = IngestText(kbRoot, args.title, args.text)
        ingested.append(dest)

    if ingested:
        UpdateCompileState(kbRoot, ingested)


if __name__ == "__main__":
    main()
