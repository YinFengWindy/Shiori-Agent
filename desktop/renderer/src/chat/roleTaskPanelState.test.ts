/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleTask } from "../shared/types";
import { groupRoleTasks, reconcileRoleTaskPanelView, reduceRoleTaskPanelView } from "./roleTaskPanelState";

function createTask(id: string, kind: RoleTask["kind"], editable = false): RoleTask {
  return {
    id,
    role_id: "mira",
    kind,
    status: editable ? "scheduled" : "running",
    label: id,
    detail: id,
    created_at: "",
    next_run_at: "",
    cancellable: kind !== "memory_maintenance",
    editable,
    schedule: kind === "schedule" ? { tier: "instant", trigger: "after", when: "1h", content: id } : null,
  };
}

describe("roleTaskPanelState", () => {
  it("groups task kinds in sidebar order", () => {
    const groups = groupRoleTasks([
      createTask("memory", "memory_maintenance"),
      createTask("subagent", "subagent"),
      createTask("schedule", "schedule", true),
    ]);

    assert.deepEqual(groups.map((group) => group.kind), ["schedule", "subagent", "memory_maintenance"]);
  });

  it("keeps empty task categories in the grouped snapshot", () => {
    const groups = groupRoleTasks([]);

    assert.deepEqual(groups.map((group) => [group.kind, group.tasks.length]), [
      ["schedule", 0],
      ["subagent", 0],
      ["memory_maintenance", 0],
    ]);
  });

  it("switches between list, detail, create, and edit views", () => {
    let view = reduceRoleTaskPanelView({ kind: "list" }, { type: "show-detail", taskId: "schedule" });
    assert.deepEqual(view, { kind: "detail", taskId: "schedule" });
    view = reduceRoleTaskPanelView(view, { type: "show-edit", taskId: "schedule" });
    assert.deepEqual(view, { kind: "edit", taskId: "schedule" });
    view = reduceRoleTaskPanelView(view, { type: "show-create" });
    assert.deepEqual(view, { kind: "create" });
    assert.deepEqual(reduceRoleTaskPanelView(view, { type: "show-list" }), { kind: "list" });
  });

  it("leaves edit when a task starts running or disappears", () => {
    const running = createTask("schedule", "schedule");
    assert.deepEqual(
      reconcileRoleTaskPanelView({ kind: "edit", taskId: "schedule" }, [running]),
      { kind: "detail", taskId: "schedule" },
    );
    assert.deepEqual(
      reconcileRoleTaskPanelView({ kind: "detail", taskId: "schedule" }, []),
      { kind: "list" },
    );
  });
});
