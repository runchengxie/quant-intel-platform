# 新机器设置

## 本地开发

安装 Python、uv 和 Git 后，在仓库根目录运行：

```bash
uv sync --locked --group dev
uv run pytest
uv run mkdocs serve
```

## 生产边界

生产凭据、定时任务、研究仓路径和投递配置由 `quant-intel-deploy` 管理。本仓只保存公开代码、示例配置、离线 fixture 和文档。
