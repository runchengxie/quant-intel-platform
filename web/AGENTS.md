# Quant Market Intel 维护约定

本文件适用于 `quant-intel-platform/web/`。同时遵循平台根目录与 `/home/richard/code/AGENTS.md` 的工作树、PR 和协作约定。

## 范围与工作方式

- `web/` 当前维护公开报告导入、快照、解读和 Pages 展示。长期定位是平台内的公开展示层。行情采集、报告内容和研究逻辑放在平台 Python 模块，生产发布和定时器归独立的 `quant-intel-deploy`。现有导入与模型脚本尚未迁移，不得把目标边界误写成已完成的事实。
- 新增功能先按职责归属放置。数据抓取、指标计算、报告写作、模型编排与证据审核优先在 platform 实现。本仓库只增加公开产物契约校验、静态渲染、下载和展示所需的适配。跨仓通过版本化公开产物或稳定 CLI 交接，不直接导入对方源码。
- 本目录已随 Git 历史并入平台仓库。迁移现有生成逻辑时，先在平台模块提供等价产物及测试，再更新 deploy 消费者和网页展示，确认生产切换及回滚路径后移除旧入口。
- 开始前只读检查工作树、分支、远端和已有 worktree，保留其他人的改动。从最新 `origin/main` 为每个独立任务创建专属分支与 worktree，只在其中开发和验证，不直接在 `main` 上开发或与其他 agent 共用工作树。
- 验证后推送任务分支并创建目标为 `main` 的 PR。完成 PR review、必需检查和冲突处理后再合并。确认 PR 已合并且 worktree 没有唯一未保存内容后，只清理本任务资源：先移除 worktree，再删除本地分支，并确认后删除远端任务分支。
- `web/` 不是 Git submodule。开发分支与 worktree 以平台仓库为单位创建。

## 目录职责

- `src/` 中的 Astro 页面负责正式展示；`src/legacy/` 保留旧页面回退材料。继续使用文本节点渲染报告和模型内容。
- `scripts/` 负责导入、构建、生成、健康检查和归档。明确区分输入数据校验失败与模型服务不可用。
- `prompts/` 维护生成口径。修改提示词后核对缓存、来源引用和数字校验行为。
- `artifacts/public/data/` 与 `artifacts/public/reports/` 仅保存可公开的近期快照，构建后的公开 URL 仍为 `/data/` 与 `/reports/`。`configs/` 仅放无密钥样例，`docs/` 记录当前用法和有日期的历史决策。

## 数据与运行边界

- 公开窗口最多保留五个不同的报告日期。目标日期、原报告生成时间、解读生成时间和部署时间分别记录。
- 只导入明确标注 `publication: public` 的 manifest。先预览，核对内容和路径后再应用。
- 私有全量归档与仓库分开。报告修订、历次解读和核验结果保留追加记录，不因公开窗口缩小而删除。
- 公开网站 CI 不读取密钥。需要密钥的模型生成留在受控发布链路，日志不输出凭据、完整请求或服务端原始错误正文。
- 本项目脚本不发送聊天消息。生产定时器引用稳定发布目录，临时工作树只用于开发和验证。
- 真实调用、历史回放、人工样例和待验证方案在文档中分别说明。构建成功、接口成功或数字校验通过，各自只证明对应环节。

## 验证与文档

根据修改范围执行相关检查，涉及共享数据契约或发布流程时执行完整检查：

```bash
python3 -m pip install --group dev
ruff check scripts tests tools
ruff format --check scripts tests tools
ty check
vulture scripts tests tools --min-confidence 80
python3 -m pytest
node --test tests/*.cjs
node --check src/legacy/app.js
python3 scripts/build_site.py --output /tmp/quant-market-intel-check
pip-audit --strict
python3 tools/audit_structure.py --output /tmp/market-intel-structure.json
```

构建会重新创建指定的输出目录，应使用仓库外的专用目录。提交前执行 `git diff --check`，界面改动补充浏览器检查。保持行与分支联合覆盖率不低于 85%，Ruff McCabe 复杂度不高于 10，不通过添加忽略项绕过问题。结构报告只覆盖静态可解析的直接调用，不视作完整运行时调用图。

README 说明现有功能与常用操作，`docs/daily-generation-options.md` 说明上游交接、运行记录和未完成事项。完成旧计划后更新其状态，保留必要决策背景，删除重复实施步骤。记录运行日期与证据，避免把计划写成已上线能力。

中文说明直接写结论和操作，使用中文标点。保留文件名、命令、字段和状态值的行内代码，减少口号、重复总结、无必要的引号与强调。页面文案只保留读者理解报告所需的信息。
