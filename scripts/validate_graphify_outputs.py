from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def _corrupted_label_ids(labels: object) -> list[str]:
    if not isinstance(labels, dict):
        raise ValueError("Graphify 标签文件必须是 JSON 对象")
    return [
        str(community_id)
        for community_id, label in labels.items()
        if not isinstance(label, str) or "??" in label or "�" in label
    ]


def main() -> int:
    """Validate that Graphify's user-facing outputs preserve UTF-8 labels."""

    parser = argparse.ArgumentParser(description="检查 Graphify 输出中的乱码标签")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("graphify-out"),
        help="Graphify 输出目录",
    )
    args = parser.parse_args()

    labels_path = args.output_dir / ".graphify_labels.json"
    report_path = args.output_dir / "GRAPH_REPORT.md"
    html_path = args.output_dir / "graph.html"

    labels_text = _read_utf8(labels_path)
    labels = json.loads(labels_text)
    corrupted_ids = _corrupted_label_ids(labels)

    corrupted_outputs = [
        path.name
        for path in (report_path, html_path)
        if "??" in _read_utf8(path) or "�" in _read_utf8(path)
    ]
    if corrupted_ids or corrupted_outputs:
        if corrupted_ids:
            preview = ", ".join(corrupted_ids[:10])
            print(f"乱码社区标签：{len(corrupted_ids)} 个，示例 ID：{preview}")
        if corrupted_outputs:
            print(f"乱码用户输出：{', '.join(corrupted_outputs)}")
        return 1

    print(f"Graphify UTF-8 验收通过：{len(labels)} 个社区标签")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
