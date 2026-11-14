# 原生 API / MCP 工作项对等交付

范围：已确认补齐方案的 A、B 阶段。MCP 使用当前 Plane 用户的原生个人访问令牌，或明确授予范围的 OAuth。没有 AI 专属角色、令牌种类或写入配额。

## 共同入口

Gateway 每次核验原始授权，再交换 Plane audience 的短期凭证，调用实际 `/api/v1/` handler。原生权限类、IssueSerializer、默认状态/负责人、字段、通知和 webhook 保存路径只有一套。原始 MCP bearer 不直接转发给 API。

`singularity/operations.py` 登记原生视图方法所需 OAuth 范围。原生 PAT 保持用户的全部原生权限；OAuth 只允许明确同意的范围。新增 `profile:read` 和 `workitems:delete`；旧 OAuth 的 `workitems:write` 不自动获得删除能力。账户停用、源 PAT 删除/过期/禁用、授权撤销及当前成员关系继续在每次调用检查。

`ApiKeyRateThrottle` 根据源 PAT UUID 或 OAuth 授权 UUID 使用 `API_KEY_RATE_LIMIT`（部署当前为 60/minute）。API 和 MCP 共享业务请求计数，委托交换不占用业务配额。已移除工作项扩展接口的额外 15/min 写限制。便捷名称解析可能实际发起项目查询；UUID + workspace 的原生工具不做这次额外查询。

## 新增工具及契约

| 工具                          | 原生入口 / 参数                                                          |
| ----------------------------- | ------------------------------------------------------------------------ |
| `get_current_user`            | `users/me/`                                                              |
| `get_project`                 | 项目详情；`summary=true` 读取摘要                                        |
| `get_project_metadata`        | `kind=states/labels/members`，原生查询参数                               |
| `list_work_items`             | 项目工作项列表；`query` 透传筛选、排序、cursor、per_page、fields、expand |
| `find_work_items`             | 工作空间原生搜索；`search`、`project_id`、`workspace_search`、`limit`    |
| `get_work_item_by_identifier` | 工作空间、项目标识、sequence_id 定位                                     |
| `create_work_item`            | `fields` 交给原生序列化器；支持幂等键                                    |
| `update_work_item`            | 原生 PATCH；只修改提交字段，支持幂等键和读取版本                         |
| `delete_work_item`            | 原生 DELETE，包括原生依赖删除行为；保留创建者/管理员检查                 |

原来的 7 个工具保留，共 16 个。`get_work_item` 现在返回原生详情（标题字段是 `name`，正文为 `description_html`），支持 `query.fields/expand`。`search_work_items` 仍是原有项目关键词便捷搜索；完整原生筛选使用 `list_work_items`，工作空间搜索使用 `find_work_items`。讨论归档、仓库授权及读取语义不变。

创建示例（工具参数中没有凭证）：

```json
{
  "workspace": "your-workspace",
  "project_id": "00000000-0000-4000-8000-000000000001",
  "idempotency_key": "client-generated-unique-operation-key",
  "fields": {
    "name": "确认交付范围",
    "description_html": "<p>已确认的业务内容</p>",
    "priority": "high",
    "start_date": "2026-11-14",
    "target_date": "2026-11-30"
  }
}
```

状态、负责人、标签、父项、估算、类型等使用原生字段 `state/assignees/labels/parent/estimate_point/type_id`，以当前原生序列化器的可写定义为准。省略字段的默认值、只读字段处理、版本/许可不支持的查询错误都与原生相同。Gateway 返回原生 400 字段错误和 409 冲突详情；不以“权限不足”代替字段错误或未实现功能。

## 所有客户端共享的重试和版本保护

原生 POST/PATCH/DELETE 接受可选 `Idempotency-Key`；MCP 对应 `idempotency_key`。成功结果及来源键在同一数据库事务保存，源凭证相同的 API/MCP 重试返回同一结果，不重复保存或发通知。相同键更改操作、项目、字段或版本返回 409。撤销及当前资源权限先于重放检查；删除重放重新检查创建者/管理员规则。记录持久化在新增 `APIMutationReceipt` 表，不能在回滚中清空。

原生 PATCH/DELETE 接受可选 `If-Match: <读取到的 updated_at>`；MCP 对应 `expected_updated_at`。比较在公共行锁内进行，网页的工作项更新也使用同一锁。旧版本返回 409，不覆盖已保存的修改。为了兼容已有 API，未提供条件的写入保留原生行为；需要防止覆盖的客户端应先读取版本并在更新时提交。幂等重放返回原响应快照，后续修改前应重新读取。

任务和 webhook 在事务提交后派发。原生通知/只读字段回归测试使用真实提交边界，保持原通知内容和权限规则。新增委托审计只记录授权引用、操作、资源、状态和 trace ID，不记录令牌或完整正文。

## 验证与部署

2026-11-14 本机结果：244 项后端契约/回归测试、22 项 Gateway 测试通过，构建、Lint 和迁移检查通过。真实 Codex 原生 MCP 完成 CRUD；Chrome 完成登录、编辑和刷新验证；30 次原生 API + 30 次 MCP 读取共同耗尽 60 次配额，随后两端均返回 429；删除 PAT 后两端拒绝。API/Gateway 重启后，原幂等键仍返回同一工作项。

- 后端契约：`plane/tests/contract/api/test_mcp_native_parity.py`，包含原生 PAT 与短期委托的角色矩阵、字段/默认值、配额、scope、撤销、并发幂等、网页编辑竞争、能力提示及 audience 检查。
- Gateway：`pnpm --filter @plane/mcp-gateway build`、`test`、`check:lint`；官方 SDK HTTP、原有仓库/讨论行为与新增工具契约。
- 数据库：生成迁移 `0132_native_api_mutation_receipts` 及迁移锁文件；`manage.py makemigrations --check --dry-run` 无缺项。
- 真实验收脚本在 `plane-ops/scripts/native-parity-{candidate,fixture,live-check,final-check}.py`、`native-parity-browser-check.cjs`。使用隔离两名用户，真实 HTTPS、DOT PKCE、原生 PAT、当前 Codex app-server 和 Chrome；不模拟服务器成功。
- 本机证据保存在受忽略的 `plane-ops/state/native-parity-candidate/`，不提交凭证或浏览器会话。UI 修改后刷新仍保留，旧版本 MCP 更新拒绝；后台活动记录显示实际状态、负责人、标签和日期变化。

部署前备份数据库和路由，先运行只读挂载候选；验收后从本地提交构建固定 API/Gateway 镜像。回滚恢复旧镜像和路由，保留新增表、工作项、授权映射和审计数据。

后续 C/D 阶段（评论、关系、周期、模块、项目管理等）以及 E 阶段附件传输不在本次 A/B 交付内。已有仓库工具保留；外部 GitHub/第二 GitLab 的授权、远程 ChatGPT 接入及公司 VPN 环境仍按原清单独立验收，不影响本次本机工作项闭环。
