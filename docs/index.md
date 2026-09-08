<div class="mi-home" markdown>

<p class="mi-eyebrow">MARKET INTELLIGENCE · RESEARCH · SYSTEMS</p>

# Market Intel

一个面向市场情报、报告、网页看板和数据契约的公开框架。

平台把市场事实、研究产物和确定性规则组合起来，生成可复现、可检查的报告产品。生产凭据、定时任务和真实运行数据由私有部署仓库管理。

<p class="mi-home__links" markdown>

[五分钟开始](getting-started.md){ .md-button .md-button--primary }
[系统架构](architecture.md){ .md-button }

</p>
</div>

## 从这里开始

如果你第一次接触这个项目，建议按下面的顺序阅读：

1. [五分钟开始](getting-started.md)：先把代码跑起来
2. [核心概念](concepts.md)：了解数据、研究产物和报告平台的关系
3. [常见任务](how-to/run-daily-report.md)：按任务查找操作步骤
4. [系统架构](architecture.md)：进一步了解平台由哪些部分组成

## 平台包含什么

| 模块 | 作用 |
| --- | --- |
| 全球市场日报 | 抓取市场与新闻，生成日报和网页看板 |
| A 股分析 | 组装市场事实，生成晨报、晚报和图表 |
| 研究产物消费 | 校验 research-workspace 发布的版本化产物 |
| 数据契约 | 约束跨模块、跨仓库的数据格式和回执 |

## 快速开始

```bash
uv sync --locked --no-dev

uv run dm --help
uv run marketops --help
uv run a-share-daily --help
```

## 贡献

提交修改前，请运行：

```bash
uv sync --locked --group dev
uv run ruff check .
uv run ty check
uv run pytest
uv run mkdocs build --strict
```

欢迎通过 GitHub issue 或 pull request 改进公开框架和文档。
