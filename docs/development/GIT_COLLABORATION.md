# Git团队协作

团队调整为六人，职责、评审与分支规则以[六人分工](TEAM_ASSIGNMENTS.md)为准。仓库已初始化为main，尚未创建提交或配置远端；下文关于未初始化的描述为此前设计阶段记录。
当前目录不是Git仓库；经设计确认开始实施时初始化并设置远端。本轮不创建分支、不提交或推送。

main保持可运行，feature/Txx-description短分支，1任务1PR，合并后删除；禁止多人共享长分支或直接推main。契约/状态/数据库变更至少一名后端与前端共同审查，其他变更一名非作者审查。数据库迁移唯一编号，已合并迁移不改写；生成的契约与源同PR。

PR模板：问题与行为变化；关联任务/设计决策；契约与迁移影响；测试结果；UI截图（若相关）；恢复/回滚步骤；已知限制。锁文件提交，API Key、.env、.flowstudio、日志、数据库和本机凭据不提交；.env.example只留占位值。

CI：Python lint/type/unit/integration，前端lint/type/unit/build，契约生成差异，Playwright关键流程；Windows runner覆盖SQLite/启动/路径边界。REAL测试只在受控密钥环境人工触发，不在fork PR暴露凭据。分支冲突先更新main再本地解决；状态枚举冲突由契约owner统一，禁止简单择一覆盖。
