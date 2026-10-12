# 运维约定

[English page](operations.md)

## 故障语义

数据不完整或外部服务不可用时，平台会记录降级状态，并在无法安全生成结果时停止后续处理。成功、降级和失败都应写入可检查的回执。

## 部署边界

主机定时任务、生产凭据、真实投递目标和运行状态由 `quant-intel-deploy` 管理。public 仓库只提供可复用的代码、契约和离线检查。

## 恢复与调度

通过稳定生产路径调用文档中的 `dm`、`a-share-daily` 和恢复脚本。定时任务不得指向临时 worktree。生产路径调整后，重新加载对应 systemd unit，并运行对应的离线或 shadow 冒烟检查。

## 质量门禁

```bash
uv run python project_tools/check_all.py --scope all
```

该入口覆盖测试、lint、类型检查、CLI 帮助同步、package coverage 和脚本检查。公开边界检查由 CI 单独运行。CI 不抓取真实市场数据，不调用飞书，也不使用券商凭据。
