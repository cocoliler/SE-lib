"""Minimal FlowStudio prototype: plan, approve, execute, review, persist."""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEMO = "设计 Windows 本地缺陷跟踪工具，支持项目、负责人和状态流转，并给出测试方案。"
ROOT = Path(__file__).resolve().parent.parent


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {"tasks"}:
        raise ValueError("计划必须是含 tasks 的 JSON 对象")
    tasks = plan["tasks"]
    if not isinstance(tasks, list) or not 2 <= len(tasks) <= 5:
        raise ValueError("计划须包含 2 到 5 项任务")
    pending = {}
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {"id", "title", "depends_on"}:
            raise ValueError("任务须包含 id、title、depends_on")
        key, title, deps = task["id"], task["title"], task["depends_on"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", key) or key in pending:
            raise ValueError("任务 ID 无效或重复")
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError("任务标题无效")
        if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
            raise ValueError("依赖必须是任务 ID 列表")
        if len(set(deps)) != len(deps):
            raise ValueError("依赖不能重复")
        pending[key] = task
    if not any(task["depends_on"] for task in tasks):
        raise ValueError("至少需要一项任务消费上游成果")
    if any(dep not in pending for task in tasks for dep in task["depends_on"]):
        raise ValueError("存在未知依赖")
    ordered = []
    finished = set()
    while pending:
        ready = [key for key, task in pending.items() if finished.issuperset(task["depends_on"])]
        if not ready:
            raise ValueError("计划依赖存在环")
        for key in ready:
            ordered.append(pending.pop(key))
            finished.add(key)
    return ordered


class AgentModel:
    def __init__(self, mode):
        self.mode = mode
        self.name = os.getenv("DEEPSEEK_MODEL", "deepseek-flash") if mode == "real" else "fixture-v1"
        self.key = os.getenv("DEEPSEEK_API_KEY", "") if mode == "real" else ""
        if mode == "real" and not self.key.strip():
            raise ValueError("REAL 模式需要设置 DEEPSEEK_API_KEY")

    def call(self, prompt, context, fixture):
        if self.mode == "test":
            return fixture(), {}
        request = Request(
            "https://api.deepseek.com/chat/completions",
            data=encode({
                "model": self.name,
                "messages": [{"role": "system", "content": prompt},
                             {"role": "user", "content": encode(context)}],
                "response_format": {"type": "json_object"},
                "max_tokens": 4096,
            }).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=60) as response:
                reply = json.loads(response.read(1_048_577))
            choice = reply["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError("模型输出未完整结束")
            return json.loads(choice["message"]["content"]), {
                "provider_request_id": reply.get("id"),
                "usage": reply.get("usage"),
            }
        except HTTPError as error:
            raise ValueError(f"DeepSeek HTTP {error.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ValueError("DeepSeek 连接失败或超时") from None
        except (TypeError, KeyError, IndexError, json.JSONDecodeError):
            raise ValueError("DeepSeek 未返回有效 JSON 成果") from None


def open_db(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, mode TEXT NOT NULL, model TEXT NOT NULL,
            goal TEXT NOT NULL, status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            run_id TEXT NOT NULL REFERENCES runs(id), seq INTEGER NOT NULL,
            kind TEXT NOT NULL, payload TEXT NOT NULL, timestamp TEXT NOT NULL,
            PRIMARY KEY (run_id, seq)
        );
    """)
    return db


def run_flow(db, model, goal, auto_approve):
    run_id = uuid.uuid4().hex
    status = "PLANNING"
    seq = 0
    with db:
        db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
                   (run_id, model.mode.upper(), model.name, goal, status))
    print(f"[{model.mode.upper()}] {model.name} | run_id={run_id}", flush=True)

    def record(kind, payload, new_status=None):
        nonlocal seq, status
        with db:
            db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                       (run_id, seq + 1, kind, encode(payload), datetime.now(timezone.utc).isoformat()))
            if new_status:
                db.execute("UPDATE runs SET status = ? WHERE id = ?", (new_status, run_id))
        seq += 1
        status = new_status or status

    try:
        plan, meta = model.call(
            '你是 Planner。拆解需求，返回 json，例如 {"tasks":[{"id":"spec","title":"分析需求",'
            '"depends_on":[]},{"id":"design","title":"设计方案","depends_on":["spec"]}]}。'
            '生成 2~5 个任务，至少一项依赖上游成果。使用小写英文 ID。',
            {"goal": goal},
            lambda: {"tasks": [
                {"id": "spec", "title": "整理需求", "depends_on": []},
                {"id": "design", "title": "起草方案与测试", "depends_on": ["spec"]},
            ]},
        )
        tasks = validate_plan(plan)
        plan_hash = hashlib.sha256(encode(plan).encode("utf-8")).hexdigest()
        record("PLAN_READY", {"plan": plan, "hash": plan_hash, **meta}, "WAITING_HUMAN")
        for task in tasks:
            deps = ", ".join(task["depends_on"]) or "无"
            print(f"  {task['id']} | {task['title']} | 依赖 {deps}")
        approved = auto_approve or input("执行此计划？输入 y 确认 [y/N] ").strip().lower() == "y"
        if not approved:
            record("PLAN_REJECTED", {"hash": plan_hash}, "CANCELED")
            print("已取消，未执行任务。")
            return 0
        record("PLAN_APPROVED", {"hash": plan_hash, "by": "test_flag" if auto_approve else "human"}, "RUNNING")

        artifacts = {}
        for task in tasks:
            key = task["id"]
            dependencies = {dep: artifacts[dep] for dep in task["depends_on"]}
            record("TASK_STARTED", {"task_id": key, "input_artifacts": list(dependencies)})
            artifact, meta = model.call(
                '你是 Worker。根据目标、任务和上游成果完成指定工作。返回 json，例如 {"summary":"成果正文"}。',
                {"goal": goal, "task": task, "dependencies": dependencies},
                lambda: {"summary": f"需求摘要：{goal}" if not dependencies else
                         f"根据上游成果「{dependencies['spec']['summary']}」制定方案：拆分业务模块，"
                         "并验证正常操作、无效输入和状态变更。"},
            )
            if (not isinstance(artifact, dict) or set(artifact) != {"summary"}
                    or not isinstance(artifact["summary"], str) or not artifact["summary"].strip()):
                raise ValueError(f"任务 {key} 的成果格式无效")
            artifacts[key] = artifact
            record("TASK_COMPLETED", {"task_id": key, "artifact": artifact, **meta})
            print(f"  完成 {key} | {artifact['summary']}")

        record("REVIEW_STARTED", {"input_artifacts": list(artifacts)}, "REVIEWING")
        review, meta = model.call(
            '你是 Reviewer。检查所有成果是否覆盖目标。返回 json，例如 '
            '{"verdict":"pass","reason":"依据"}。覆盖不足时 verdict 使用 fail。',
            {"goal": goal, "plan": plan, "artifacts": artifacts},
            lambda: {"verdict": "pass", "reason": "TEST 检查：两项成果齐全，下游引用了上游需求摘要。"},
        )
        if (not isinstance(review, dict) or set(review) != {"verdict", "reason"}
                or review["verdict"] not in ("pass", "fail")
                or not isinstance(review["reason"], str) or not review["reason"].strip()):
            raise ValueError("审查结果格式无效")
        status = "COMPLETED" if review["verdict"] == "pass" else "FAILED"
        record("REVIEW_COMPLETED", {"review": review, **meta}, status)
        print(f"{status} | Reviewer: {review['reason']}")
        return 0 if status == "COMPLETED" else 1
    except (EOFError, KeyboardInterrupt):
        record("RUN_CANCELED", {}, "CANCELED")
        print("已取消。", file=sys.stderr)
        return 130
    except ValueError as error:
        record("RUN_FAILED", {"stage": status, "error": str(error)}, "FAILED")
        print(f"FAILED | {error}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("test", "real"), default="test")
    parser.add_argument("--goal", default=DEMO)
    parser.add_argument("--approve", action="store_true", help="仅 TEST 模式可自动批准")
    parser.add_argument("--db", type=Path, default=ROOT / ".flowstudio" / "prototype.db")
    args = parser.parse_args()
    if args.approve and args.mode != "test":
        parser.error("--approve 仅限 TEST 模式")
    if not 1 <= len(args.goal.strip()) <= 4000:
        parser.error("需求长度须为 1 到 4000 字符")
    try:
        model = AgentModel(args.mode)
        with closing(open_db(args.db)) as db:
            return run_flow(db, model, args.goal.strip(), args.approve)
    except (ValueError, sqlite3.Error, OSError) as error:
        print(f"无法运行原型 | {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
