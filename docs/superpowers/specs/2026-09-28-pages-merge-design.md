# 市场日报网页并入平台设计

日期：2026-09-28

## 目标与现状

将 `quant-intel-pages` 的公开日报网站并入 `quant-intel-platform`，使数据契约、报告生产和展示代码在一个仓库内维护。日报成为 `https://runchengxie.github.io/quant-intel-platform/` 首页。现有 MkDocs 文档迁到 `/quant-intel-platform/docs/`。近期报告、历史晨晚报、来源链接、Markdown、纯文本和图表均需继续可用。

目前 platform 已在其 GitHub Pages 根路径发布 MkDocs。Pages 仓库独立部署 Astro 日报，且仍含导入、快照、模型解读脚本。两个生产发布器将公开报告提交到 Pages 仓库，并从其稳定发布目录调用导入脚本。合并必须同时处理网站构建、发布器路径、模型密钥和旧站退场，不能只复制前端源码。

## 选择的结构

第一阶段以保留提交历史的 Git subtree 把 Pages 项目纳入 platform 的 `web/`，保持 `web/pyproject.toml`、`web/package.json`、`web/src/`、`web/scripts/`、`web/prompts/`、`web/tests/` 与 `web/artifacts/public/` 的内部相对路径。旧仓库暂时保留，既可查历史也可回滚。platform 根目录的 Python 包和 `web/` 各运行自己的质量门禁，不把网页依赖加入市场数据服务包。

网站使用一次构建、一次 Pages 部署。先把 Astro 日报与经过校验的公开快照构建到站点根目录，再把 MkDocs 严格构建到该输出的 `docs/` 子目录。Astro 基址改为 `/quant-intel-platform/`，MkDocs 的 `site_url` 改为 `/quant-intel-platform/docs/`。只有统一 workflow 能调用 `actions/deploy-pages`，避免两套工作流互相覆盖。

第二阶段把导入、简评和模型编排逐项移入 platform 的报告模块，`web/` 只保留公开产物校验、静态渲染与下载。跨模块仍使用带版本、目标日期、来源、审核状态和内容哈希的产物契约。第一阶段先保留原脚本，保证网站合并不改变新闻核实与缺项边界。

## 发布与配置

先合并 platform 的网站与统一构建 PR，在新地址做只读影子验证，旧站继续发布。再修改 `quant-intel-deploy` 的两个发布器，使机器人检出 platform 仓库并只提交 `web/artifacts/public/` 白名单。导入脚本从稳定的 platform 发布目录下 `web/scripts/` 调用。更新生产环境、机器人检出与定时器时须检查 pending 状态，逐项试跑并保留回滚目录。

Pages 仓库的 Gemini、DeepSeek、MiniMax Secrets 不能自动随代码迁移。正式切换前，在 platform 仓库配置同名 Secrets，按名称及最小成功探测验证，不记录密钥值。Codex CLI 仍在本机发布器运行。缺少模型 Secrets 时不得把回退能力写成已恢复。

平台站点和两个发布器连续通过验证后，旧 `quant-intel-pages` 站点改为指向新首页的跳转页；旧仓库暂不删除或归档，以保留回滚路径和完整历史。旧报告直链是否能逐项重定向应单独验证，无法重定向时在切换记录中列明。

## 门禁与回滚

平台根目录现有 Python 全量门禁保持有效，`web/` 用原有 Python、Node、静态构建和公开数据契约测试。统一 Pages workflow 在 PR 中只构建与检查，不部署；合并到 `main` 后才部署。核对首页、文档首页、报告正文、下载、图表、深色模式及手机布局，比较新旧站同一公开报告的日期和内容哈希。

生产切换前保存当前 platform、deploy、Pages 发布 SHA 与仓库外配置备份。新站部署失败时恢复 platform 上一个文档站发布版本；发布器失败时恢复原 Pages 仓库、稳定发布目录和环境配置，再启用旧定时器。不要清理其他任务的 worktree、分支或私有归档。

## 非目标

本次不重写日报内容、不改变新闻事实审核规则、不补造缺项、不迁移私有原始数据，不删除旧仓库或历史报告。对数据和模型逻辑的进一步拆分在站点和发布链路稳定后另行实施。
