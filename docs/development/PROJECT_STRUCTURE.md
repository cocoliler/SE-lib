# 工程组织与契约管理
## 当前与目标目录
当前仓库跟踪frontend，main没有backend业务代码；prototype目录本地只有缓存，不是可运行后端。CLI历史原型在独立分支。
以下为待开发目标：
```text
frontend/src/
  app/                       # 工作区和路由
  features/spec/
  features/planning/
  features/workflow/         # 现有画布逐步拆分
  api/generated/             # OpenAPI生成，不手改
  styles/tokens.css
backend/
  app/api/
  app/application/           # 用例、命令、PlanningRun协调
  app/domain/                # DTO、纯验证和拓扑
  app/agents/pm/
  app/providers/
  app/persistence/           # SQLAlchemy仓储
  migrations/
contracts/                   # 实施后生成OpenAPI/JSON Schema
tests/unit/ integration/ e2e/ live/
docs/contracts/              # 当前设计Schema附件
# 本轮不增加产品案例或预设模板目录
```

## 单一契约
设计期以docs/contracts Schema和架构语义为准；Phase1建立Pydantic实现并生成contracts/OpenAPI及TS。切换时将设计Schema改为生成产物或指向生成文件，不长期双手维护。
CI检查导出无差异、未知字段拒绝、Schema样例可解析。依赖关系规则不假装能全部写成JSON Schema，Python验证器与前端快速检查共享案例。
目录调整按功能逐步拆分，不为设计一次性搬动main.tsx。
