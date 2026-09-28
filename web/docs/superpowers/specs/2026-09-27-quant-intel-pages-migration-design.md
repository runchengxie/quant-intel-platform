# Quant Intel Pages 更名与目录迁移设计

日期：2026-09-27

## 目标与边界

将公开网站仓库更名为 `runchengxie/quant-intel-pages`，本地主要检出移至 `/home/richard/code/quant/quant-intel-pages`，并收敛仓库根目录。网站仍提供中国时间 07:00 美股复盘、19:00 亚洲收盘复盘、近期历史和经核实的公开材料。用户接受旧 GitHub Pages 项目网址 `/market-intel-pages/` 失效，新网址为 `/quant-intel-pages/`。

这次只迁移路径和命名，不改行情口径、报告结构、公开审核规则、五日期窗口或定时发布时间。私有全量归档、凭据和构建输出仍在仓库外。仓库更名与本地目录移动不等于生产部署完成，生产切换需单独验证。

## 目录方案

| 位置 | 内容与规则 |
|---|---|
| `src/pages/`、`src/components/`、`src/lib/`、`src/styles/` | 正式 Astro 网站代码。根目录共用 JS 按用途迁入 `src/lib/`；不新增 `web/`。 |
| `src/legacy/` | 旧 HTML、JS、CSS 回退页面。保留现有行为，但不再把其文件散放在仓库根目录或当作正式首页。 |
| `artifacts/public/data/`、`artifacts/public/reports/` | 现有纳入 Git 的五日期公开快照和原文。仅允许通过公开校验的内容，不能放私有候选或凭据。 |
| `configs/.env.example` | 无密钥的本地配置样例。实际密钥放在仓库外。 |
| `scripts/`、`prompts/`、`tests/`、`docs/`、`tools/` | 各自保持原职责。 |
| 仓库根目录 | 保留 `package.json`、`package-lock.json`、`pyproject.toml`、`astro.config.mjs`、`AGENTS.md`、`README.md`、`.github/` 等工具和平台约定入口。 |

`artifacts/public/` 是受版本控制的公开发布输入，不是构建输出。完整历史归档、运行日志和 Pages 构建目录继续放仓库外。浏览器路径仍为 `/data/…`、`/reports/…`，不暴露仓库内部 `artifacts/public/` 前缀。报告 JSON 的 `source_url` 继续使用公开相对路径 `reports/<id>.md`，由单一安全路径解析函数映射到仓库内的 `artifacts/public/reports/`；任何绝对路径、上级穿越或非 `reports/` 前缀仍拒收。

## 配置与发布数据流

本地真实配置由调用者通过明确环境变量或环境文件传入，不在代码中拼接用户名。Richard 机器可以沿用 `~/.config/richard/`，其他机器可使用各自的 XDG 配置目录；样例只负责说明变量格式，移动后更新 README 中的复制命令。不会把已有密钥复制进仓库。

导入器将经过审核的公开清单写到 `artifacts/public/`；构建器读取该目录，校验报告、图表和美股日报的身份、日期、来源及数量限制，再复制到临时 Pages 输出根目录的 `data/`、`reports/`。Astro 从临时输出读取数据并覆盖首页与逐期页。校验或构建失败时，不替换已有输出，也不发布不完整页面。旧版回退页面若继续随产物提供，应位于 `/legacy/`，且不得覆盖 Astro 首页。

## 更名与跨仓切换

1. 在 Pages 仓库独立分支中迁移目录、修改导入／构建／Astro／Actions 路径和测试，完成本地与 PR 检查后合并。代码须能针对新站点路径构建完整产物。
2. 对 GitHub 仓库执行更名，更新各检出的 `origin`，触发并核对 Pages 在 `/quant-intel-pages/` 的真实发布。旧项目网址不设自动重定向，所有本项目维护的导航和下载链接转向新路径。
3. 在私有 `quant-intel-deploy` 独立 PR 中更新发布器的仓库名、网址及路径样例和测试，合并后再切换生产配置。切换前后检查定时任务、公开日报 PR、Pages 实际 URL 和失败恢复。生产环境变更须获得该仓库要求的独立授权。
4. 只有任务分支已合并、工作树没有独有内容，才将主要本地检出移入 `quant/`。先清理本任务已合并的 worktree；若其他人的关联 worktree 仍在使用，暂停本地移动并协调，不能擅自迁移 Git 管理目录。检查稳定生产 release、发布器 checkout 与脚本是否引用旧绝对路径，不依赖临时开发 worktree。不要删除其他 agent 的工作树或分支。

GitHub 仓库链接会随更名重定向，但 GitHub Pages 项目网站链接不会。切换期间如检查不通过，保留旧生产配置和可回滚的 release；不把更名成功当作网站已发布或定时发布已恢复。

## 验证与完成条件

- 迁移前后同一公开快照的报告数量、日期、正文、图表与数据质量状态一致；私有候选仍不能进入产物，路径穿越仍被拒绝。
- Python、Node、Astro 构建、静态检查、结构审计和依赖审计按 Pages 仓库 `AGENTS.md` 执行；增加针对内部路径与公开 URL 分离的测试，检查旧版 `/legacy/` 回退页面和无 JS 时的主要信息。
- 私有部署仓库按自身 `AGENTS.md` 跑本地质量门禁、发布器冒烟和无发送检查，不为了普通提交反复触发 Actions。
- 实际访问新站首页、至少一份报告页、Markdown／纯文本下载和图表资源；检查移动端与深色模式。发布器下一次符合条件的批次能向新仓库建 PR，并在合并后刷新新站。若尚未观察到真实定时批次，明确记录为待验证，不宣称自动发布已通过。

## 不采用的方案

- 不新增 `web/`：Astro 已使用 `src/`，再嵌套一层会改动工具工作目录和导入路径，却不增加清晰度。
- 不把所有 JSON、JS、CSS 按扩展名搬运：依赖清单与 Astro 配置必须留在工具约定位置，公开 JSON 属于快照，不属于配置。
- 不把真实密钥或完整历史搬进 `configs/`、`artifacts/public/`；不建立自动发布未经审阅候选的捷径。
