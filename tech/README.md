# FlowStudio 统一契约

需要 Python 3.11 或较新的兼容版本（实测 3.14.2）。在 `contracts` 目录运行以下命令生成契约产物：

```powershell
python -m pip install -r requirements.txt
python scripts/export_contracts.py
```

`python scripts/export_contracts.py --check` 只比对不写盘，产物与模型不一致时返回 1。

1. `flowstudio_contracts/` 是唯一事实源：严格 Pydantic 模型，定义设计规格、任务提案、校验报告、规划运行、计划版本、布局与接口 DTO。
2. `artifacts/schema/` 是可通用的 JSON Schema，PM 输出、编排校验、落库前检查都按它判定；`artifacts/openapi.json` 是接口契约，后端按它实现路由。
3. 前端不手写类型：`../frontend/src/api/generated/contracts.ts` 由同一模型生成，业务代码从 `../frontend/src/api/contracts` 引用。
4. 改契约的唯一正确方式：改模型 → 重新生成 → 一起提交；手改 `artifacts/` 或 `generated/contracts.ts` 会被 `--check` 覆盖。

`artifacts/examples/` 是 9 个合法样例（规格、候选、运行、派生结果、计划、布局、错误体），供前端 mock 与联调基线；它不是产品模板库，默认规划只依据用户输入的规格。

契约层只做结构与跨字段不变量，不含 HTTP 服务、数据库与模型调用；任务唯一性、依赖存在性、环检测、需求覆盖率属于编排器。当前仓库没有后端，因此"规格 → 任务分解 → 编排 → 可视化"尚未端到端跑通。

## 设计文档

`docs/` 下是本模块的两份设计交付，合并自原 `docs/architecture/` 的 18 篇专题：

| 文件 | 内容 |
|---|---|
| `tech/docs/tech-stack.md` | 选型总表、ADR 001–012、实测锁定版本、未验证清单、参考项目研究、证据边界与许可 |
| `tech/docs/system-architecture.md` | 架构总览、分层规则、模块划分、领域模型、编排算法、接口层、数据库、实现现状、P2 扩展 |

两份文档自包含、无跨文件链接。它们描述设计，不含可执行代码；本模块可运行的部分只有 `flowstudio_contracts/` 与 `artifacts/`。
