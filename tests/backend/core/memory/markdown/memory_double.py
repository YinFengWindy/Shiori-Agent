"""In-memory source/result fixture for host commit and undo ordering tests."""


class CommittedMemory:
    def __init__(self, source_ids):
        self.source_ids = list(source_ids)
        self.items = {}

    def upsert_item(self, **values):
        item_id = str(len(self.items) + 1)
        self.items[item_id] = {"id": item_id, "status": "active", **values}
        return "new:" + item_id

    def get_items_by_ids(self, ids):
        return [self.items[item_id] for item_id in ids]

    def undo_by_message_sources(self, ids, *, dry_run=False):
        affected = list(self.items) if set(ids).intersection(self.source_ids) else []
        if not dry_run:
            for item_id in affected:
                self.items[item_id]["status"] = "superseded"
        return {
            "affected_ids": affected,
            "restored_ids": [],
            "rollback_source_ids": self.source_ids if affected else [],
        }

    def close(self):
        pass
