# FlowStudio P0 交付报告

交付日期：2026-11-18

代码基线：`1a7feef`

验收分支：`feature/f/T08-acceptance`

## 交付范围

本交付完成课堂作业 2 的 P0 闭环：

```text
Design Spec → PM Agent → Task Decomposition
→ Deterministic Orchestration → Workflow Visualization
→ Editable PlanRevision → Persistence / Export
```

本次不包含 P2 实际任务执行、工具调用、审批、SSE、成果验证和多 Agent 监督。相关范围仍按
[MVP_SCOPE](../docs/product/MVP_SCOPE.md)执行。

## 入口

| 内容 | 位置 |
|---|---|
| 产品与启动说明 | [README](../README.md) |
| Windows 部署 | [LOCAL_DEPLOYMENT](../docs/development/LOCAL_DEPLOYMENT.md) |
| P0 验收状态 | [P0_CLOSURE_REPORT](../docs/testing/P0_CLOSURE_REPORT.md) |
| REAL 验收 | [REAL_ACCEPTANCE_REPORT](../docs/testing/REAL_ACCEPTANCE_REPORT.md) |
| 质量属性 | [QUALITY_ACCEPTANCE_REPORT](../docs/testing/QUALITY_ACCEPTANCE_REPORT.md) |
| 需求追踪 | [REQUIREMENTS_TRACEABILITY](../docs/product/REQUIREMENTS_TRACEABILITY.md) |
| 设计评审 | [DESIGN_REVIEW](../docs/DESIGN_REVIEW.md) |

GitHub Actions 参考配置位于
[github-actions-verify.yml.example](github-actions-verify.yml.example)。按“他人项目”的交付边界，
它默认不激活；仓库所有者批准后可复制到 `.github/workflows/verify.yml`。

验收判据只以 `docs/testing/ACCEPTANCE_TESTS.md`、需求追踪矩阵和质量属性文档为准；
本报告只汇总交付状态。

## 验收结论

| 范围 | 结果 |
|---|---|
| A01–A12 P0 | 12/12 通过，含 REAL、人工语义评审与进程重启 |
| R01–R18 | P0 需求完成；R18 越界检查通过 |
| Q01–Q08 | 在记录环境全部通过 |
| TEST 统一门禁 | 14/14 步骤通过 |
| P0 HTTP | 项目隔离、规格版本、坏图、编排、冲突、导出与重启通过 |

关键实测：

- 后端：197 通过，1 项 REAL 守卫测试按设计跳过
- T05：53 通过
- 编排：100 任务/1000 边 p95 `6.456ms`
- 持久化：100 任务保存 p95 `42.902ms`，失败无部分写入
- 画布：100 任务/200 边首屏 `220.3ms`，拖动平均 `58.6fps`
- REAL：`deepseek-flash`、`pm-v1`，多次运行均在预算和时限内

## 复现

首次安装与核心 TEST 验证：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1 -Bootstrap
```

包含质量基准：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1 -Quality
```

启动应用：

```powershell
Set-Location backend
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

另开终端：

```powershell
Set-Location frontend
npm.cmd run dev
```

REAL 验收单独执行，避免默认测试产生外部费用：

```powershell
Set-Location backend
python scripts\real_acceptance.py --base-url http://127.0.0.1:8000 `
  --spec ..\delivery\inputs\campus-meeting-spec.json `
  --evidence <仓库外证据.json>
```

随包参考输入的规范化内容 hash 为
`66912432ab4f35b338e2b8c06a582722bd920a796879974195206f3ceae60691`；
它只作为 REAL 验收输入，不是默认产品模板。

## 证据

最近一次完整门禁：

```text
evidence/runs/20261118-155653/
```

证据内容：

- `summary.md`、`summary.json`
- 全量命令日志
- P0 HTTP 与重启状态
- 浏览器规格、工作流和深色主题截图
- Q02/Q03 与 Q04/Q08 测量 JSON
- REAL 验收在 `evidence/runs/20261118-stage4-real/`

`evidence/runs/` 已被 Git 忽略，避免提交数据库、日志和用户输入副本。

生成源码与证据交付包：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_delivery.ps1
```

## 人工签字

| 项目 | 结果 |
|---|---|
| F 技术审查 | 通过 |
| 非模块作者语义评审 | 朱志伟，通过，2026-11-18 |
| 真实模型验收 | A04/A11 技术通过 |
| P0 正式状态 | 关闭 |

PR 合并仍需团队 Review。合并前按
[Git 协作规范](../docs/development/GIT_COLLABORATION.md)确认非作者审批。

## 已知风险

1. 成功 `PlanningRun` 未暴露供应商 request ID；当前以 run ID、attempt、usage、候选和报告为证据。
2. 性能结果只代表当前 Windows 测试环境，不外推所有硬件和浏览器。
3. `npm audit` 的 4 个 high 均位于 Vite 开发工具链，生产依赖审计为 0；不得用强制主版本降级修复。
4. P2 执行、工具权限、审批和运行恢复尚未实现，不纳入本次交付承诺。

## 交付检查

- [x] P0 与质量验收完成
- [x] REAL 与人工语义评审完成
- [x] 统一门禁与 CI 入口
- [x] 验收证据和复现命令
- [x] 分支已推送 GitHub
- [ ] 仓库所有者决定是否启用 GitHub Actions
- [ ] PR 已完成团队 Review 并合并
