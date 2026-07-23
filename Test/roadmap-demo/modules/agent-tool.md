---
id: agent-tool
title: 工具系统
aliases:
  - 工具
  - tool
  - grep
  - 文件工具
  - ToolComponent
roots:
  - agent/component/tool
entrypoints:
  - ToolComponent
  - BaseTool
  - GrepCodeTool
related:
  - agent-core
summary: "文件/Shell/网络等工具注册与调度"
---

## 职责

工具注册、调度、文件搜索（glob/grep）等。

## 结构

- 入口：`toolComponent.py`
- 文件工具：`file/`
