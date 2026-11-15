# artifacts — 生成产物（请勿手改）

由 `tech/scripts/export_contracts.py` 从 `flowstudio_contracts` 的 Pydantic 模型生成。
手改会被 `--check` 立刻发现。

| 路径 | 内容 |
|---|---|
| `schema/*.schema.json` | 13 个自查式 JSON Schema（Draft 2020-12，自包含 `$defs`） |
| `openapi.json` | OpenAPI 3.1，14 条路径 / 18 个操作 |
| `manifest.json` | Schema 版本、规则版本与每个产物的 SHA-256 |
| `examples/*.json` | 9 个合法样例：规格、候选（含阻塞）、运行（成功/失败）、派生结果、计划、布局、错误体 |

```powershell
python tech/scripts/export_contracts.py           # 重新生成
python tech/scripts/export_contracts.py --check   # 只检查漂移
```

`examples` 是契约夹具，用于前端 mock 与 `fixture_id` 显式选择的 TEST 运行；
它不是产品模板库，也不参与默认规划输入。用途与边界见
[统一契约实现与协作流程](../../docs/development/CONTRACT_WORKFLOW.md)。
