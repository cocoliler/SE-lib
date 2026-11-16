"""进程内有界规划队列（单消费者）。

- 上限默认 10；超限由 API 返回 429 QUEUE_FULL。
- 持久化先于入队：进程中断时由启动恢复标记 FAILED，不假装可靠任务队列。
- inline 模式用于测试（提交即同步执行）。
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

LOGGER = logging.getLogger(__name__)


class PlanningQueueFull(Exception):
    pass


class PlanningQueue:
    def __init__(self, capacity: int, handler: Callable[[str], None], mode: str = "thread") -> None:
        if mode not in {"thread", "inline"}:
            raise ValueError("worker_mode 只能是 thread 或 inline")
        self.capacity = max(1, capacity)
        self.mode = mode
        self._handler = handler
        self._queue: queue.Queue[str] = queue.Queue(maxsize=self.capacity)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def has_capacity(self) -> bool:
        return self.mode == "inline" or self._queue.qsize() < self.capacity

    def submit(self, run_id: str) -> None:
        if self.mode == "inline":
            self._run_guarded(run_id)
            return
        try:
            self._queue.put_nowait(run_id)
        except queue.Full as exc:  # pragma: no cover - API 已预检
            raise PlanningQueueFull("规划队列已满") from exc

    def start(self) -> None:
        if self.mode != "thread" or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="planning-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                run_id = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._run_guarded(run_id)
            finally:
                self._queue.task_done()

    def _run_guarded(self, run_id: str) -> None:
        try:
            self._handler(run_id)
        except Exception:  # noqa: BLE001 - 后台消费不允许影响进程
            LOGGER.exception("规划任务处理失败：%s", run_id)
