# 研究平台发布产物消费

`market-intel` 可以读取 `research-workspace` 生成的 `research.platform-publication.v1` 产物包，不需要引入研究方的实现代码。

## 作用

发布清单是一份交接索引。`market-intel` 通过它定位已经审核过的投影结果，并将结果渲染为报告、投递卡片或操作页面。

消费方会检查以下内容：

- 通过锁定版本的 `research-contracts` 包检查清单结构
- 检查是否明确声明了 `market-intel` 消费方
- 检查披露范围（`public` 或 `internal`）
- 检查产物包内的相对路径是否安全
- 检查文件是否存在
- 检查 SHA-256 内容哈希

`verify_platform_publication()` 返回已经解析并验证过的路径。它不会加载模型对象，不会调用研究方内部代码，也不会猜测缺失的产物。

## 披露模式

当部署环境明确属于内部环境时，运行任务或生成报告可以使用 `allow_internal=True`。只面向公开内容的渲染必须使用 `allow_internal=False`。如果某个内部产物被明确标记为只供 `market-intel` 使用，校验会安全失败。

## 与现有产物的关系

DailyWatch20、style-factor、D11-H5 以及其他已经建立的契约继续有效。发布清单为未来跨系统使用研究结果提供统一外壳，也不会取代各策略自己的校验规则。

## 发布过程

当前改动依赖 `research-workspace` 的 platform-publication 契约分支。合并前需要完成以下事项：

1. 合并上游工作区的契约改动
2. 将 `research-contracts` 锁定到工作区 `main` 的最新提交
3. 运行 `uv lock` 并提交更新后的 `uv.lock`
4. 运行 `market-intel` 的常规质量检查

## 接近生产环境的测试样例

`tests/fixtures/publications/daily_watch20/` 包含一个模拟的内部 DailyWatch20
产物包，里面有观察列表、选股回执和发布清单。它使用与实际部署交接相同的消费路径，
同时不会把真实证券代码、数据供应商数据、凭据和私有路径带入仓库。这个测试样例在
`allow_internal=True` 时必须通过，在只面向公开内容的消费模式下必须安全失败。
