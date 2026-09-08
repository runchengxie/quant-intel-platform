<div class="mi-hero" markdown>

<div class="mi-eyebrow">PUBLIC MARKET INTELLIGENCE FRAMEWORK</div>

# Market Intel

把市场事实、研究产物和可审计契约，组合成可复现的情报产品。

<div class="mi-hero__actions" markdown>

[开始使用](configuration.md){ .md-button .md-button--primary }
[查看系统架构](architecture.md){ .md-button }

</div>
</div>

<div class="mi-stats" markdown>

<div class="mi-stat" markdown>
<span class="mi-stat__value">01</span>
<span class="mi-stat__label">Public framework</span>
</div>
<div class="mi-stat" markdown>
<span class="mi-stat__value">03</span>
<span class="mi-stat__label">CLI entrypoints</span>
</div>
<div class="mi-stat" markdown>
<span class="mi-stat__value">∞</span>
<span class="mi-stat__label">Versioned contracts</span>
</div>

</div>

## 平台能力

<div class="mi-grid" markdown>

<div class="mi-card mi-card--cyan" markdown>

### `GLOBAL / INTEL`

全球市场、主题评分、新闻上下文与日报渲染。

[了解日报 →](architecture.md#全球市场日报daily-messenger)

</div>

<div class="mi-card mi-card--amber" markdown>

### `A-SHARE / ANALYTICS`

A 股市场事实、市场温度、报告组装与确定性图表。

[了解分析 →](a-share-factor-signals.md)

</div>

<div class="mi-card mi-card--blue" markdown>

### `CONTRACTS / ARTIFACTS`

跨仓公开 CLI、版本化 artifact 与边界契约。

[阅读契约 →](contracts.md)

</div>

<div class="mi-card mi-card--gold" markdown>

### `PUBLIC / QUALITY`

Public-safe CI、离线测试、边界检查和可复现构建。

[查看边界 →](public-release/public-boundary.md)

</div>

</div>

## 快速开始

```bash
uv sync --locked --no-dev

uv run dm --help
uv run marketops --help
uv run a-share-daily --help
```

从[系统架构](architecture.md)开始了解模块边界，再阅读[跨仓边界契约](boundary-contract.md)和[配置说明](configuration.md)。

## 文档导航

- [系统架构](architecture.md)：流水线、数据源和仓库结构
- [数据契约](contracts.md)：公开 artifact 和接口约定
- [CLI 参考](cli-reference.md)：命令行入口与参数
- [测试](testing.md)：离线测试与质量门
- [Public boundary](public-release/public-boundary.md)：public 与 private deployment 的责任边界

## 贡献

提交前请运行：

```bash
uv sync --locked --group dev
uv run ruff check .
uv run ty check
uv run pytest
uv run mkdocs build --strict
```

欢迎通过 GitHub issue 或 pull request 改进公开框架和文档。
