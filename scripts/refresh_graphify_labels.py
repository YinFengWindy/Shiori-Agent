from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


_DOMAIN_RULES = (
    (("plugins/novelai/", "core/integrations/novelai/"), "NovelAI 图像"),
    (("plugins/akasha/",), "Akasha 记忆"),
    (("plugins/default_memory/", "core/memory/", "memory2/"), "记忆系统"),
    (("core/roles/",), "角色系统"),
    (("session/",), "会话运行时"),
    (("conversation/",), "对话持久化"),
    (("proactive_v2/",), "主动行为"),
    (("agent/core/drift_turn.py",), "Drift 回合"),
    (("agent/mcp/",), "MCP 集成"),
    (("agent/tools/", "agent/tool_"), "Agent 工具"),
    (("agent/plugins/",), "Agent 插件"),
    (("agent/lifecycle/",), "Agent 生命周期"),
    (("agent/background/",), "后台 Agent"),
    (("agent/core/", "agent/turns/", "agent/looping/"), "Agent 运行时"),
    (("desktop_bridge/",), "桌面桥接"),
    (("desktop/renderer/",), "桌面界面"),
    (("desktop/src/",), "Electron 桌面"),
    (("infra/channels/", "plugins/qqbot/", "core/channels/"), "渠道系统"),
    (("bus/",), "消息总线"),
    (("bootstrap/",), "启动装配"),
    (("core/integrations/",), "外部集成"),
    (("core/common/", "infra/persistence/", "utils/"), "公共基础"),
    (("coding_agents/",), "编码 Agent"),
    (("prompts/",), "提示词系统"),
    (("plugins/",), "插件系统"),
    (("docs/", "CONTEXT.md"), "项目知识"),
    (("scripts/",), "开发脚本"),
    (("agent/",), "Agent 系统"),
    (("core/",), "核心领域"),
    (("infra/",), "基础设施"),
)

_GENERIC_HUB_LABELS = {
    "Any",
    "Config",
    "E",
    "None",
    "Path",
    "T",
    "ValueError",
    "dict",
    "list",
    "object",
    "set",
    "str",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8", errors="strict"))


def _domain_for_source(source_file: str) -> str:
    normalized = source_file.replace("\\", "/").lstrip("./")
    for prefixes, domain in _DOMAIN_RULES:
        if normalized.startswith(prefixes):
            return domain
    return "项目模块"


def _is_clean_label(label: object) -> bool:
    return isinstance(label, str) and "??" not in label and "�" not in label


def _hub_label(nodes: list[dict[str, Any]], degrees: Counter[str]) -> str:
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for node in nodes:
        label = str(node.get("label") or "").strip()
        if not label or not _is_clean_label(label) or len(label) > 60:
            continue
        node_id = str(node.get("id") or "")
        source_location = str(node.get("source_location") or "")
        score = (
            0 if label in _GENERIC_HUB_LABELS else 1,
            0 if source_location in {"", "L1"} else 1,
            degrees[node_id],
        )
        candidates.append((score, label))
    if not candidates:
        return "社区"
    return max(candidates, key=lambda item: item[0])[1]


def _community_domain(nodes: list[dict[str, Any]]) -> str:
    source_files = {
        str(node.get("source_file") or "")
        for node in nodes
        if node.get("source_file")
    }
    domains = Counter(_domain_for_source(source_file) for source_file in source_files)
    if not domains:
        return "跨模块"
    non_default = [(domain, count) for domain, count in domains.items() if domain != "项目模块"]
    return max(non_default, key=lambda item: item[1])[0] if non_default else "项目模块"


def _write_json_atomic(path: Path, data: dict[str, str]) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def main() -> int:
    """Regenerate deterministic UTF-8 community labels from graph structure."""

    parser = argparse.ArgumentParser(description="刷新 Graphify 中文社区标签")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("graphify-out"),
        help="Graphify 输出目录",
    )
    args = parser.parse_args()

    graph_path = args.output_dir / "graph.json"
    labels_path = args.output_dir / ".graphify_labels.json"
    graph = _load_json(graph_path)
    existing_labels = _load_json(labels_path) if labels_path.exists() else {}

    degrees: Counter[str] = Counter()
    for edge in graph.get("links", []):
        degrees[str(edge.get("source") or "")] += 1
        degrees[str(edge.get("target") or "")] += 1

    communities: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for node in graph.get("nodes", []):
        community_id = node.get("community")
        if isinstance(community_id, int):
            communities[community_id].append(node)

    labels: dict[str, str] = {}
    used_labels: set[str] = set()
    for community_id in sorted(communities):
        existing_label = existing_labels.get(str(community_id))
        if _is_clean_label(existing_label) and any(
            "\u4e00" <= character <= "\u9fff" for character in existing_label
        ):
            label = existing_label
        else:
            domain = _community_domain(communities[community_id])
            hub = _hub_label(communities[community_id], degrees)
            label = f"{domain} · {hub}"
        if label in used_labels:
            label = f"{label}（{community_id}）"
        labels[str(community_id)] = label
        used_labels.add(label)

    _write_json_atomic(labels_path, labels)
    print(f"已刷新 {len(labels)} 个 UTF-8 社区标签：{labels_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
