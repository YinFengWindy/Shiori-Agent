/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { ScheduledTask } from "./types";
import { formatBlockView, parseBlockView, reconcileBlockView, type ScheduleBlockView } from "./blockView";

function task(id: string, editable: boolean): ScheduledTask {
  return {
    id,
    role_id: "mira",
    status: editable ? "scheduled" : "running",
    label: id,
    detail: id,
    created_at: "",
    next_run_at: "",
    editable,
    schedule: { tier: "instant", trigger: "after", when: "1h", content: id },
  };
}

describe("blockView", () => {
  it("round-trips every view through the host's token, a job id with colons included", () => {
    const views: ScheduleBlockView[] = [
      { kind: "list" },
      { kind: "create" },
      { kind: "detail", taskId: "a:b" },
      { kind: "edit", taskId: "job-1" },
    ];
    for (const view of views) assert.deepEqual(parseBlockView(formatBlockView(view)), view);
    assert.deepEqual(parseBlockView("unknown:job-1"), { kind: "list" });
  });

  it("leaves edit when a job starts running and the job's views when it disappears", () => {
    assert.deepEqual(reconcileBlockView({ kind: "edit", taskId: "job" }, [task("job", false)]), { kind: "detail", taskId: "job" });
    assert.deepEqual(reconcileBlockView({ kind: "detail", taskId: "job" }, []), { kind: "list" });
    // Before the first read a view stands.
    assert.deepEqual(reconcileBlockView({ kind: "detail", taskId: "job" }, null), { kind: "detail", taskId: "job" });
  });
});
