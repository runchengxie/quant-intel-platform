<div class="mi-home" markdown="1">

[English page](index.md)

<p class="mi-eyebrow">QUANT MARKET INTEL / 文档</p>

# 使用与方法

从公开日报开始，逐步了解报告如何生成、数据如何核对，以及各模块负责什么。

生产凭据、定时任务和真实运行数据由私有部署仓库管理。

<p class="mi-home__links" markdown="1">

[五分钟开始](getting-started.md){ .md-button .md-button--primary }
[阅读最新日报](https://runchengxie.github.io/quant-intel-pages/){ .md-button }

</p>
</div>

## 按需要阅读

初次使用，先从快速开始进入；需要核对报告或维护系统时，直接看对应路径。

1. **运行日报**：从[五分钟开始](getting-started.md)和[运行市场日报](how-to/run-daily-report.md)进入。
2. **理解与核对**：阅读[核心概念](concepts.md)、[数据契约](contracts.md)和[来源说明](public-release/data-provenance.md)。
3. **维护平台**：查看[系统架构](architecture.md)、[运维说明](operations.md)和[测试](testing.md)。

## 文档范围

| 模块 | 作用 |
| --- | --- |
| 全球市场日报 | 抓取市场与新闻，生成日报和网页看板 |
| A 股分析 | 组装市场事实，生成晨报、晚报和图表 |
| 研究产物消费 | 校验 owner 发布的版本化产物 |
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
