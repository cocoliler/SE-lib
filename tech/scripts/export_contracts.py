"""生成契约产物（JSON Schema / OpenAPI / TS 类型 / 样例）。

用法：
    python tech/scripts/export_contracts.py           # 写入
    python tech/scripts/export_contracts.py --check   # 只比对，漂移返回 1

产物位置：`tech/artifacts/`（TS 类型写入 `frontend/src/api/generated/` 供前端消费）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

OWNER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = OWNER_ROOT.parent
if str(OWNER_ROOT) not in sys.path:
    sys.path.insert(0, str(OWNER_ROOT))

from flowstudio_contracts.export import build_artifacts  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出 FlowStudio 契约产物")
    parser.add_argument("--check", action="store_true", help="只检查产物是否与模型一致，不写盘")
    parser.add_argument("--root", default=str(REPO_ROOT), help="仓库根目录，默认脚本所在仓库")
    args = parser.parse_args(argv)
    root = Path(args.root)

    artifacts = build_artifacts()
    drifted: list[str] = []
    for relative, content in sorted(artifacts.items()):
        target = root / relative
        if args.check:
            existing = target.read_text(encoding="utf-8") if target.exists() else None
            if existing != content:
                drifted.append(relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")

    if args.check:
        if drifted:
            print("契约产物与模型不一致：")
            for relative in drifted:
                print(f"  - {relative}")
            print("请运行 python tech/scripts/export_contracts.py 重新生成后提交。")
            return 1
        print(f"契约产物一致：{len(artifacts)} 个文件。")
        return 0

    print(f"已生成 {len(artifacts)} 个契约文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
