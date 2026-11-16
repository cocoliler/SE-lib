# TEST fixture 目录

TEST 模式的规划请求必须显式指定 `fixture_id`，服务端只会读取本目录下同名 JSON 文件；
未知 fixture 直接 422，不会静默伪造结果。

文件名即 fixture ID，例如 `diamond.json` → `fixture_id="diamond"`。

文件内容必须是一个合法的 **TaskProposal**：

```json
{
  "schema_version": "1.0",
  "tasks": [
    {
      "task_id": "A",
      "name": "示例任务",
      "description": "任务说明",
      "category": "design",
      "stage": "design",
      "priority": "medium",
      "assigned_role": "architect",
      "dependencies": [],
      "inputs": [],
      "deliverables": [{"id": "doc", "text": "交付说明"}],
      "acceptance_criteria": ["结果可观察"],
      "source_requirement_ids": ["R1"],
      "rationale": "",
      "assumptions": [],
      "estimated_effort": null
    }
  ],
  "blocking_questions": []
}
```

约定：

- `blocking_questions` 非空或存在 `impact=critical` 的假设 → PlanningRun 进入 `NEEDS_INPUT`。
- 结构或图校验失败 → `FAILED`，错误码 `MODEL_SCHEMA`。
- 本目录**不放产品案例或预设模板**；fixture 只用于结构验证与前端联调。
- fixture 注册属于 C 的 T04 范围，当前实现只按文件名读取，后续由真实 Provider 替换。
