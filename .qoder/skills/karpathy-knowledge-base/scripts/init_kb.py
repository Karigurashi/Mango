"""初始化 Karpathy 风格 LLM 知识库目录结构。

Usage:
    python scripts/init_kb.py <kb_root> [--name "My KB"]

Example:
    python scripts/init_kb.py ./my-research --name "ML Research Wiki"
"""

import argparse
import json
import os
import sys
from datetime import datetime


def InitKnowledgeBase(rootPath: str, kbName: str = "Knowledge Base") -> None:
    """在 rootPath 下创建标准知识库目录结构。"""
    dirs = [
        os.path.join(rootPath, "raw"),
        os.path.join(rootPath, "wiki", "concepts"),
        os.path.join(rootPath, "output"),
        os.path.join(rootPath, "_meta"),
    ]

    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"  ✓ 创建目录: {d}")

    # 创建 .gitkeep 占位
    for d in [os.path.join(rootPath, "raw"), os.path.join(rootPath, "output")]:
        gitkeep = os.path.join(d, ".gitkeep")
        with open(gitkeep, "w", encoding="utf-8") as f:
            pass

    # 创建 wiki/INDEX.md
    indexPath = os.path.join(rootPath, "wiki", "INDEX.md")
    with open(indexPath, "w", encoding="utf-8") as f:
        f.write(f"# {kbName}\n\n")
        f.write(f"创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## 概念索引\n\n")
        f.write("| 概念 | 摘要 | 来源 | 最后编译 |\n")
        f.write("|------|------|------|----------|\n")
        f.write("| (待编译) | — | — | — |\n")
    print(f"  ✓ 创建文件: {indexPath}")

    # 创建 _meta/compile_state.json
    statePath = os.path.join(rootPath, "_meta", "compile_state.json")
    initialState = {
        "kbName": kbName,
        "createdAt": datetime.now().isoformat(),
        "lastCompiled": None,
        "totalConcepts": 0,
        "totalArticles": 0,
        "processedFiles": {},
        "compileLog": [],
    }
    with open(statePath, "w", encoding="utf-8") as f:
        json.dump(initialState, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 创建文件: {statePath}")

    print(f"\n知识库 '{kbName}' 初始化完成: {os.path.abspath(rootPath)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="初始化 Karpathy 风格 LLM 知识库目录结构",
    )
    parser.add_argument("root", help="知识库根目录路径")
    parser.add_argument("--name", default="Knowledge Base", help="知识库名称")
    args = parser.parse_args()

    rootPath = os.path.abspath(args.root)
    if os.path.exists(rootPath) and os.listdir(rootPath):
        print(f"警告: 目录 '{rootPath}' 已存在且非空")
        resp = input("是否继续? 不会覆盖已有文件 (y/N): ")
        if resp.lower() != "y":
            print("已取消")
            sys.exit(0)

    InitKnowledgeBase(rootPath, args.name)


if __name__ == "__main__":
    main()
