from __future__ import annotations

from pathlib import Path

from plugins.akasha.backend.store import AkashaStore, SourceMessage


def _index(store: AkashaStore, role_id: str, seqs: list[int]) -> None:
    """Index same-timestamp user turns for one role, in the given order."""
    for seq in seqs:
        store.upsert_message_node(
            SourceMessage(
                id=f"role:{role_id}:{seq}",
                session_key=f"role:{role_id}",
                seq=seq,
                role="user",
                content=f"text {seq}",
                ts="2026-01-01T00:00:00+00:00",
            ),
            [1.0, 0.0],
        )


def test_list_items_for_admin_breaks_time_ties_by_key(tmp_path: Path) -> None:
    store = AkashaStore(tmp_path / "akasha.db")
    try:
        # 倒序写入，使 rowid 顺序与 key 顺序相反。
        seqs = [16, 14, 12, 10, 8, 6, 4, 2, 0]
        _index(store, "mira", seqs)
        expected = sorted(f"role:mira:{seq}" for seq in seqs)

        for sort_order in ("asc", "desc"):
            ids: list[object] = []
            for page in range(1, 6):
                items, total = store.list_items_for_admin(
                    role_id="mira",
                    page=page,
                    page_size=2,
                    sort_by="happened_at",
                    sort_order=sort_order,
                )
                assert total == len(expected)
                ids.extend(item["id"] for item in items)
            assert ids == expected
    finally:
        store.close()


def test_list_items_for_admin_matches_like_wildcards_literally(
    tmp_path: Path,
) -> None:
    store = AkashaStore(tmp_path / "akasha.db")
    try:
        _index(store, "mira", [0, 2])

        percent, percent_total = store.list_items_for_admin(role_id="mira", q="%")
        underscore, _ = store.list_items_for_admin(role_id="mira", q="_")
        literal, _ = store.list_items_for_admin(role_id="mira", q=":2")

        assert (percent, percent_total) == ([], 0)
        assert underscore == []
        assert [item["id"] for item in literal] == ["role:mira:2"]
    finally:
        store.close()


def test_admin_items_do_not_use_key_as_summary(tmp_path: Path) -> None:
    store = AkashaStore(tmp_path / "akasha.db")
    try:
        _index(store, "mira", [0])

        items, _ = store.list_items_for_admin(role_id="mira")
        detail = store.get_item_for_admin("role:mira:0")

        assert [(item["id"], item["summary"]) for item in items] == [
            ("role:mira:0", "")
        ]
        assert detail is not None
        assert detail["summary"] == ""
    finally:
        store.close()
