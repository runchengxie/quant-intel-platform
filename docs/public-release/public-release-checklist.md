# Public 发布检查清单

创建或更新 public GitHub 仓库前，请完成以下检查。生产历史应继续保留在私有仓库，直到全部检查完成。

## 发布记录

发布前，在私有 deploy 仓库记录以下值：

- `source_revision`：私有源码中最后审核通过的 commit
- `public_revision`：clean export 的根 commit
- `public_release_tag`：不可变的 public release tag
- `deploy_platform_pin`：deploy 使用的 40 位 commit
- `rollback_platform_pin`：已验证可回滚的 40 位 commit

## 仓库边界

- [ ] `file-migration-manifest.yml` 已覆盖所有 tracked file
- [ ] public 源码只使用语义化受众名称
- [ ] 生产调度、恢复桥和主机配置文件已放入私有仓库
- [ ] public 源码不导入、checkout 或依赖私有部署代码
- [ ] public 源码不使用隐含的生产文件路径

## 数据与隐私

- [ ] public tree 中没有真实客户、合作方、群组、用户或内部文档标识
- [ ] public tree 中没有真实 webhook、chat ID、token、凭据、私有端点或代理标签
- [ ] `state/`、`out/`、回执、日志和服务商快照均未发布
- [ ] public fixture 是合成数据，或已确认拥有再分发权限
- [ ] Git history 已完成密钥和私有标记扫描

## 依赖与构建

- [ ] public CI 所需的运行时依赖无需私有权限即可解析
- [ ] `research-contracts` 可通过公开包、release 或仓库获取
- [ ] public package 可从 clean export 构建
- [ ] 私有 deploy 已锁定不可变的 public release

## CI 与验证

- [ ] public CI 不依赖仓库 secrets
- [ ] public CI 不访问真实行情接口、飞书、私有网络或生产路径
- [ ] boundary checker 通过
- [ ] lint、format、类型检查、测试、CLI 检查和 package build 通过
- [ ] 私有 deploy 已针对 public release 完成 dry-run 验证

## 发布后

- [ ] license 和依赖声明已检查
- [ ] branch protection 和 GitHub Actions 权限已检查
- [ ] README 和贡献指南完整
- [ ] 私有 deploy 已记录 rollback release
- [ ] public 仓库由 clean history 创建，没有直接修改私有仓库的可见性
