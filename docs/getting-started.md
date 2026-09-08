# 五分钟开始

这篇文档带你完成一次本地安装和离线检查。整个过程不需要市场服务商凭据，也不会发送消息。

## 1. 准备工具

请先安装：

- Python 3.11、3.12 或 3.13
- Git
- uv

## 2. 安装项目

```bash
git clone https://github.com/runchengxie/quant-intel-platform.git
cd quant-intel-platform
uv sync --locked --group dev
```

`uv sync` 会创建本地虚拟环境并安装项目依赖。依赖版本由 `uv.lock` 固定。

## 3. 查看命令

```bash
uv run dm --help
uv run marketops --help
uv run a-share-daily --help
```

这三个入口分别用于全球市场日报、数据任务和 A 股报告。

## 4. 跑一次测试

```bash
uv run pytest
```

测试使用仓库中的离线 fixture，不访问生产数据。

## 5. 启动文档站

```bash
uv run mkdocs serve
```

打开终端显示的本地地址，通常是 `http://127.0.0.1:8000/`。

## 下一步

- 想了解整体流程，阅读[核心概念](concepts.md)
- 想运行日报，阅读[运行市场日报](how-to/run-daily-report.md)
- 想生成看板，阅读[生成网页看板](how-to/build-dashboard.md)
- 想配置数据路径，阅读[配置说明](configuration.md)
