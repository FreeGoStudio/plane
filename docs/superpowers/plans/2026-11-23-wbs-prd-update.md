# PRD 修改后的 WBS 更新实施记录

依据：用户确认的四阶段方案，以及“未确认 PRD 可先分析、确认后执行”“开发中任务逐项选择”的明确决定。

## 验收与实施顺序

- [x] 后端：固定 PRD 与正文来源；首次生成、替代草稿、未开发调整、开发中逐项决策；过期版本、幂等与事务测试。
- [x] 前端和 MCP：统一更新入口、差异展示、来源确认状态和逐项动作；共享审批校验。
- [x] 验证：隔离后端测试、Gateway 测试、类型检查、页面检查、独立审查。

## 边界

仅修改 Plane 业务仓库，不扩展旧工作台、不部署生产、不推送。保留历史任务与审批，未受影响任务不修改。开发进度不等于代码已验收；缺实现证据明确标注。

## 接口决策

既有 WBS 请求保持兼容；新增 mode=update 使用版本化变更契约。snapshot 保存来源、前版与子任务状态；result 保存变更清单；批准携带 choices 和正文确认。文档确认复用 RequirementAdoption completed 记录及对应内容摘要。

实施决定：新增 execution JSON 字段及 0141 迁移，将获批动作、人工替代任务和执行前后证据独立保存，避免修改不可变输入摘要。若审批人将取消建议改为更新/追加，需填写并确认完整任务内容；不能把无内容的取消建议当成可执行新任务。

## 进度

原始仓库 preview 工作区干净，基线 44cead48ec。独立工作树 codex/wbs-prd-update。
Storybook 未安装，不为本次 UI 修改新增工具链；使用现有组件、类型检查与页面验证。

## 验证记录

- 原基线 WBS 11 项通过。新增测试先验证缺失行为失败，再实现通过；独立审查发现的版本基准、开发历史、空正文和空引用问题均补充失败复现并修正。
- 后端隔离回归 67 项和新增混合状态专项 1 项通过，覆盖 WBS、PRD 审查、四阶段处理、混合状态、事务回滚、重复批准、迟到 Worker、历史接口及人工替代任务。命令：`pytest plane/tests/contract/api/test_wbs_update.py plane/tests/contract/api/test_wbs.py plane/tests/contract/api/test_requirement_review.py -q`，以及 `pytest plane/tests/contract/api/test_wbs_update.py -k mixed_task -q`。
- Gateway 32 项通过，前端动作规则 3 项通过；页面使用实际 WbsPanel/WbsChanges 和现有 Button、CSS，外部服务使用隔离夹具。验证首次发起、未确认 PRD 禁止批准、逐项选择、取消改追加的内容要求，以及桌面/390px 布局。
- React 页面检查无应用控制台错误，移动端无横向溢出。没有在生产工作项执行真实批准。
- 全局 i18n 检查存在既有 886 个缺项（20 个非中文简体目标语言），本次新增 21 个键在全部 22 个语言中齐全；机器翻译尚未经过各语言母语审校。不扩修既有缺项。
- 后端 Hatchet SDK 的四条既有弃用警告，以及前端 Vite/ESM 配置提示保留；不作为本功能新增失败。
- `pnpm --filter web check:types`、受影响前端/Gateway 的 oxlint（零警告）、后端 ruff、`makemigrations --check --dry-run` 和 `git diff --check` 通过。独立审查修复后复核无新增阻塞项。
- 实现与上述自动验证完成；真实 PRD 采用、人工业务批准及生产部署未执行。保留功能分支，不推送或合并。
