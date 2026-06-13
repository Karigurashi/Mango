---
name: karpathy-knowledge-base
description: 通用 LLM 知识库管理工具。将任意文档（论文、网页、知乎、博客、笔记等）编译为结构化 Wiki 知识网络。提供初始化、摄入、编译、查询、健康检查全流程脚本。当用户需要管理知识、构建知识库、整理文档、或提到 "Karpathy wiki"、"知识库"、"知识编译"、"knowledge base" 时使用。
---

# LLM 知识库管理工具

## 适用场景

论文整理、知乎收藏、技术博客、读书笔记、产品调研、竞品分析、学习资料 …… 任何文档丢进来，LLM 自动编译成互联的知识网络。

## 全流程速览

```
1. init     创建知识库目录     python scripts/init_kb.py <kb路径>
2. ingest   丢入源文档          python scripts/ingest.py <kb路径> --file/--dir/--url/--text
3. compile  LLM 编译为 Wiki    python scripts/compile.py <kb路径>
4. query    提问查询           python scripts/query.py <kb路径> "问题"
5. health   质量检查           python scripts/health_check.py <kb路径>
```

## 一、初始化知识库

```bash
# 基本用法
python scripts/init_kb.py <知识库路径> --name "知识库名称"

# 示例
python scripts/init_kb.py ./my-research --name "机器学习研究"
python scripts/init_kb.py ./reading-notes --name "读书笔记"
python scripts/init_kb.py D:/kb/competitor --name "竞品情报"
```

**参数说明：**

| 参数 | 必填 | 说明 |
|------|:--:|------|
| `kb路径` | ✓ | 知识库根目录，不存在则自动创建 |
| `--name` | | 知识库名称，显示在 INDEX.md 顶部，默认 "Knowledge Base" |

**执行后自动创建：**

```
<kb路径>/
├── raw/                    ← 源文档存放处（你丢文件的地方）
├── wiki/
│   ├── INDEX.md            ← 概念总索引
│   └── concepts/           ← 编译后的概念文章
├── output/                 ← 查询结果输出
└── _meta/
    └── compile_state.json  ← 编译进度记录
```

---

## 二、摄入文档

把源文档放入 `raw/`。支持四种方式：

### 2.1 摄入单个文件

```bash
python scripts/ingest.py <kb路径> --file <文件路径>

# 示例
python scripts/ingest.py ./my-research --file ~/Downloads/attention-paper.pdf
python scripts/ingest.py ./my-research --file ./notes/transformer.md
python scripts/ingest.py ./my-research --file "D:/知乎收藏/如何理解反向传播.md"
```

### 2.2 批量摄入目录

```bash
python scripts/ingest.py <kb路径> --dir <目录路径>

# 示例：一次性导入整个论文文件夹
python scripts/ingest.py ./my-research --dir ~/Papers/2024/
python scripts/ingest.py ./my-research --dir ./clippings/
```

递归扫描目录下所有文件，自动跳过隐藏文件（`.` 开头）。

### 2.3 从 URL 抓取网页

```bash
python scripts/ingest.py <kb路径> --url <网页地址>

# 示例
python scripts/ingest.py ./my-research --url "https://zhuanlan.zhihu.com/p/xxxxx"
python scripts/ingest.py ./my-research --url "https://arxiv.org/abs/1706.03762"
python scripts/ingest.py ./my-research --url "https://blog.example.com/llm-guide"
```

**依赖：** 需要 `pip install requests`，推荐 `pip install markdownify`（自动将 HTML 转为 Markdown）。

### 2.4 直接写入文本

```bash
python scripts/ingest.py <kb路径> --text "文本内容" --title "文档标题"

# 示例
python scripts/ingest.py ./my-research --text "反向传播通过链式法则计算梯度..." --title "反向传播笔记"
```

### 2.5 摄入后的效果

- 文件复制到 `raw/` 目录（重名自动加后缀 `_1`, `_2`）
- 自动计算文件 MD5 哈希，记录到 `_meta/compile_state.json`
- 标记为 "待编译"，等待下一步 compile

---

## 三、LLM 编译（核心步骤）

将 `raw/` 中的源文档通过 LLM 编译为 `wiki/` 中的结构化概念文章。

### 3.1 基本编译

```bash
# 增量编译（默认）——只处理新增和变更的文件
python scripts/compile.py <kb路径>

# 示例
python scripts/compile.py ./my-research
```

### 3.2 编译选项

```bash
# 强制全量重新编译（忽略编译状态）
python scripts/compile.py <kb路径> --force

# 预览模式：只看哪些文件待编译，不实际执行
python scripts/compile.py <kb路径> --dry-run

# 指定 LLM 模型
python scripts/compile.py <kb路径> --model gpt-4

# 指定 LLM 配置文件
python scripts/compile.py <kb路径> --config /path/to/models.json
```

**参数说明：**

| 参数 | 说明 |
|------|------|
| `--force` | 强制重新编译所有 raw/ 文件 |
| `--dry-run` | 预览模式，只列出待编译文件，不实际调用 LLM |
| `--model` | 指定模型名（需在 `models.json` 中配置） |
| `--config` | LLM 配置文件路径，默认 `worksapce/models.json` |

### 3.3 编译产出

每篇源文档经 LLM 处理后，生成：

```
wiki/concepts/<概念名>.md
```

文章格式：

```markdown
---
title: 概念名称
category: 方法论
related: [关联概念A, 关联概念B]
confidence: high
last_compiled: 2026-05-31
---

# 概念名称

> 一句话摘要

详细的 Wiki 文章内容，包含 [[wiki-links]] 指向关联概念...

## 关键事实

- 事实 1
- 事实 2
```

同步更新 `wiki/INDEX.md`（概念索引表）和 `_meta/compile_state.json`（编译进度）。

### 3.4 增量编译机制

- 首次运行：编译所有 raw/ 文件
- 后续运行：对比文件 MD5 哈希，只编译新增或变更的文件
- 新摄入文档后直接 `compile.py` 即可增量更新

---

## 四、查询知识库

对编译好的 Wiki 提问，LLM 自动检索相关概念后综合回答。

### 4.1 单次查询

```bash
python scripts/query.py <kb路径> "你的问题"

# 示例
python scripts/query.py ./my-research "Transformer 的自注意力机制如何工作？"
python scripts/query.py ./my-research "BERT 和 GPT 的架构区别是什么？"
```

### 4.2 交互式查询

```bash
python scripts/query.py <kb路径> -i

# 进入交互模式后：
#   输入问题 → 回车查询
#   输入 concepts → 查看所有概念列表
#   输入 quit/exit/q → 退出
```

### 4.3 查询选项

```bash
python scripts/query.py <kb路径> "问题" --model gpt-4
python scripts/query.py <kb路径> "问题" --config /path/to/models.json
```

### 4.4 查询流程（两阶段）

1. **概念选择**：LLM 查看 `wiki/INDEX.md`，选出与问题相关的概念（最多 8 个）
2. **综合回答**：读取选中概念的完整文章作为上下文，LLM 综合回答

---

## 五、健康检查

定期审计知识库质量，发现问题。

### 5.1 基础检查

```bash
python scripts/health_check.py <kb路径>

# 检查项：
#   - 孤立概念（没有被其他文章引用的概念）
#   - 瘦文章（正文少于 200 字符的概念）
#   - 断链（引用不存在概念的 [[wikilinks]]）
#   - 缺失来源（frontmatter 中没有 sources 字段）
#   - 过时概念（超过 30 天未更新）
```

### 5.2 深度检查（LLM 审计）

```bash
python scripts/health_check.py <kb路径> --deep

# 额外执行：
#   - LLM 扫描概念文章，发现跨文章的陈述矛盾
#   - 输出矛盾位置、严重程度、修复建议
```

### 5.3 检查选项

```bash
python scripts/health_check.py <kb路径> --model gpt-4
python scripts/health_check.py <kb路径> --config /path/to/models.json
python scripts/health_check.py <kb路径> --deep --model claude-3
```

---

## 六、典型工作流

### 场景 A：整理知乎收藏

```bash
# 1. 创建知识库
python scripts/init_kb.py ./zhihu-kb --name "知乎收藏"

# 2. 批量抓取收藏的文章
python scripts/ingest.py ./zhihu-kb --url "https://zhuanlan.zhihu.com/p/111"
python scripts/ingest.py ./zhihu-kb --url "https://zhuanlan.zhihu.com/p/222"
python scripts/ingest.py ./zhihu-kb --url "https://zhuanlan.zhihu.com/p/333"

# 3. 编译
python scripts/compile.py ./zhihu-kb

# 4. 查询
python scripts/query.py ./zhihu-kb -i
# > "这些文章里关于深度学习的核心观点是什么？"
```

### 场景 B：论文文献综述

```bash
# 1. 初始化
python scripts/init_kb.py ./lit-review --name "文献综述"

# 2. 批量导入论文文件夹
python scripts/ingest.py ./lit-review --dir ~/Downloads/papers/

# 3. 预览待编译文件
python scripts/compile.py ./lit-review --dry-run

# 4. 确认后编译
python scripts/compile.py ./lit-review

# 5. 查询研究方法对比
python scripts/query.py ./lit-review "这些论文中使用的方法有哪些？各自优劣？"
```

### 场景 C：竞品情报持续追踪

```bash
# 1. 初始建库
python scripts/init_kb.py ./competitor --name "竞品情报"

# 2. 摄入初始资料
python scripts/ingest.py ./competitor --dir ./initial-data/

# 3. 首次全量编译
python scripts/compile.py ./competitor

# 4. 定期摄入新信息
python scripts/ingest.py ./competitor --url "https://competitor.com/blog/new-feature"
python scripts/ingest.py ./competitor --text "竞品A 发布了新定价..." --title "竞品A 2026Q2 更新"

# 5. 增量编译
python scripts/compile.py ./competitor

# 6. 每周健康检查
python scripts/health_check.py ./competitor --deep
```

### 场景 D：个人读书笔记

```bash
# 1. 建库
python scripts/init_kb.py ./book-notes --name "读书笔记"

# 2. 边读边记
python scripts/ingest.py ./book-notes --text "第一章核心观点：..." --title "《XX书》第一章"
python scripts/ingest.py ./book-notes --text "第二章核心观点：..." --title "《XX书》第二章"

# 3. 读完编译
python scripts/compile.py ./book-notes

# 4. 回顾查询
python scripts/query.py ./book-notes "这本书的核心论点是什么？各章如何论证？"
```

---

## 七、注意事项

1. **raw/ 只放不改**：源文档放入后不要手动编辑，改动后 compile 会自动检测重编译
2. **wiki/ 不要手动改**：所有 wiki 文件由 LLM 生成和维护，手动改会在下次编译时被覆盖
3. **Markdown 格式最佳**：LLM 对 Markdown 理解最好，PDF/Word 建议先转 Markdown 再摄入
4. **首次编译较慢**：取决于文件数量和 LLM 速度，后续增量编译很快
5. **可 Git 版本管理**：整个知识库是纯文本，`git init && git add . && git commit` 即可版本控制
6. **LLM 费用**：每次编译调用 LLM API，大文件多文件注意 token 消耗
