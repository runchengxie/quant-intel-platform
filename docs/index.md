# Market Intel

Market Intel 是一个面向市场情报、报告、网页看板和数据契约的公开框架。

它负责把市场上下文、版本化 artifact 和确定性渲染组合成可复现的报告产品。生产环境中的凭据、定时调度、真实状态、投递配置和部署细节属于私有 deployment context，不包含在本 public repository 中。

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
