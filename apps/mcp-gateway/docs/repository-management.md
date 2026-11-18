# Plane 项目仓库创建与成员管理

需求依据：新建项目时自动创建并绑定项目文档、Storybook 原型仓库；项目设置保留手动修改以支持迁移和地址变化；独立管理身份管理成员权限，日常执行账号继续禁止建仓。

## 实现行为

启用功能后，新建 Project 在同一次数据库事务中记录初始化意图，独立管理进程创建两个私有仓库并绑定到 documentation / prototype 字段。开发代码仓库仍按项目实际组成登记多个，不猜测仓库数量。

路径为 `plane-{project_uuid_hex}-{documentation|prototype}`。先持久化操作标识再请求 GitLab；响应丢失后按固定路径和标识恢复。人工绑定优先，重试不覆盖；同路径标识不符时停止，不另建替代仓库。自动创建仓库带 README 和 main 分支，main 禁止直接推送、Maintainer 可合并；不改动人工登记仓库的分支策略。

项目设置提供初始化状态与重试、仓库路径修改、专用绑定切换、成员权限表。服务端校验浏览器会话、CSRF、项目管理员和修订号。管理进程与配置写入共用项目级 PostgreSQL advisory lock；锁忙返回冲突供重试。MCP 与日常执行连接器不增加建仓或权限管理接口。

## 成员权限

| Plane 项目角色 | 默认 GitLab 项目权限 |
| -------------- | -------------------- |
| Admin          | Maintainer（40）     |
| Member         | Developer（30）      |
| Guest          | Reporter（20）       |

管理员可按仓库、成员覆盖为默认、移除直接授权、Reporter、Developer 或 Maintainer。周期同步要求项目成员、工作空间成员及用户均有效。退出项目、停用仓库或切换专用绑定后，只撤销旧目标中由平台管理的直接授权；reference 仓库不参与同步。

成员身份来源必须是同实例经验证的 RepositoryIdentity，或实例 URL 匹配的已关联 CompanyAccount；缺失时等待验证，不按姓名或邮箱猜测。个人读取凭据仍归本人，管理凭据不进入个人连接。

外部直接授权默认保留，管理员可显式“接管此直接授权”，同时核验修订号和观察到的直接权限。托管后出现外部改动时保留并显示冲突。继承权限不能通过移除直接授权消除，界面显示实际权限，不自动改动群组成员关系。初始化 ready 只表示两个槽位就绪，成员同步结果另看各成员状态。

## 部署接入

当前为源码交付和自动验证，未部署或写入真实 GitLab。

1. 在现有 RepositoryInstance 登记目标 GitLab，保留 TLS 和私网允许列表；运行包含 `0135_repository_management` 的数据库迁移。
2. 专用服务身份需有目标群组创建项目、保护分支、管理成员所需权限及 API 令牌。只给独立管理进程挂载令牌文件，不挂载到 API、MCP、执行进程或前端。服务身份不可同时作为日常执行身份。
3. API 与独立管理进程使用相同非秘密配置：

   ```dotenv
   SINGULARITY_REPOSITORY_PROVISIONING_ENABLED=1
   SINGULARITY_REPOSITORY_MANAGEMENT_INSTANCE_ID=<Plane中登记的实例UUID>
   SINGULARITY_REPOSITORY_MANAGEMENT_GROUP_ID=<GitLab数字群组ID>
   ```

4. 使用 API 同版本镜像、数据库连接和 Django 配置启动独立服务，配置失败自动重启，不开放端口：

   ```sh
   python manage.py run_repository_provisioner --secret-file /run/secrets/gitlab_repository_manager_token
   ```

   默认常驻轮询；`--once` 只处理当前到期任务。每轮重新读取令牌文件，支持轮换；令牌内容不放入命令行、日志或仓库。

5. 群组建仓级别须为受限的 maintainer、owner 或版本支持的 administrator。程序检查执行身份的有效群组级别；已达建仓门槛则不新增项目授权并报告配置错误。项目 Maintainer 与群组 Maintainer 不同，本功能只授予前者。已有公司账号的 `projects_limit=0`、`can_create_group=false` 和 Workbench 建仓禁令保留。GitLab 全局管理员及其他群组的外部特权需由运维排除，平台不会擅自撤销外部授权。
6. 启用前已有项目不批量建仓，由管理员在项目设置点击初始化。已绑定槽位复用，缺失槽位才创建。关闭开关并停止进程可停止自动处理，保留仓库、绑定和审计记录。

## 手动迁移

- 同仓库改名/路径变化：编辑“仓库设置”路径，用当前管理员自己的连接核验 GitLab project ID 不变；专用仓库追加绑定历史。
- 换仓库或 GitLab 实例：先登记替代仓库，再在“专用仓库绑定”选择并保存。新绑定成为执行入口，不删除旧仓库，也不自动搬运内容。
- 实例域名变化：实例管理员通过已有登记接口注册新地址，再登记仓库并重绑；个人连接、证书和私网允许列表需对应新实例，不把任意 URL 当身份。项目设置不直接改写实例级主机配置。
- 权限管理仅写入已配置的同实例、同群组。其他实例/群组可绑定并用于日常执行，但显示不在管理范围，不将旧管理令牌发到新主机。
- 初始化操作冻结实例和群组。改变全局管理目标不会静默重定向旧操作，而是报告 configuration_changed。跨管理域迁移需部署新域身份并制定已记录操作的迁移步骤，不能直接覆盖操作身份。

## 验证与待验收

| 原始验收点       | 自动验证                                                                        | 最终环境验收             |
| ---------------- | ------------------------------------------------------------------------------- | ------------------------ |
| 自动创建并绑定   | 原生项目 POST、事务回滚、响应丢失恢复、重试不重复创建                           | 待真实 GitLab 验证       |
| 手动修改与迁移   | 同 ID 改路径、不同 ID 要求重绑、人工绑定优先、旧仓库保留                        | 待真实迁移演练           |
| 成员管理         | 角色同步、撤销托管授权、继承保留、显式接管、外部改动、身份/CSRF/管理员/修订检查 | 待真实双用户验收         |
| 日常账号禁止建仓 | 执行连接器 5 项回归、管理凭据隔离、群组门槛检查                                 | 待真实账号和群组配置核验 |

相关后端 65 项契约测试、迁移一致性、Ruff、前端 TypeScript 和定向 OxLint 通过。隔离浏览器用真实 React 组件验证初始化、接管、路径修改、绑定保存、修订冲突和成员只读，零页面异常；API 使用桩，不能替代真实 GitLab 验收。

新增文案覆盖 22 个语言文件，状态为 machine_translated，母语审阅待完成。全量 i18n 检查仍报告多数语言原有的 886 个缺键；本次 repository namespace 键一致，不扩展修复无关文案。

接口参考：[Groups API](https://docs.gitlab.com/api/groups/)、[Projects API](https://docs.gitlab.com/api/projects/)、[Project members API](https://docs.gitlab.com/api/project_members/)、[Protected branches API](https://docs.gitlab.com/api/protected_branches/)。
