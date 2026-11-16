"""单实例文件锁：防止两个后端进程操作同一数据库。

进程退出时操作系统自动释放锁，不需要清理陈旧锁文件。
"""

from __future__ import annotations

import os
from pathlib import Path


class InstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    _LOCK_OFFSET = 1024

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")  # noqa: SIM115 - 生命周期由锁对象管理
        # 先写定长 pid（Windows 上被锁定的字节区间不可写），再锁偏移 1024 的 1 个字节
        try:
            handle.seek(0)
            handle.write(f"{os.getpid()}\n".encode("ascii").ljust(32, b" "))
            handle.flush()
            if os.name == "nt":  # Windows
                import msvcrt

                handle.seek(self._LOCK_OFFSET)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # POSIX
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError(
                f"已有 FlowStudio 后端在使用同一数据目录（{self.path}），请先关闭它"
            ) from exc
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(self._LOCK_OFFSET)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            handle.close()
            self._handle = None
