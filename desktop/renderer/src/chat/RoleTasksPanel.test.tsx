/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { RoleTask } from "../shared/types";
import { groupRoleTasks, RoleTasksPanel } from "./RoleTasksPanel";

function createTask(overrides: Partial<RoleTask>): RoleTask {
  return {
    id: overrides.id ?? "task-1",
    role_id: overrides.role_id ?? "mira",
    kind: overrides.kind ?? "schedule",
    status: overrides.status ?? "scheduled",
    label: overrides.label ?? "提醒",
    detail: overrides.detail ?? "喝水",
    created_at: overrides.created_at ?? "2026-07-11T10:00:00+00:00",
    next_run_at: overrides.next_run_at ?? "2026-07-11T11:00:00+00:00",
    cancellable: overrides.cancellable ?? true,
  };
}

describe("groupRoleTasks", () => {
  it("groups task kinds in sidebar order", () => {
    const groups = groupRoleTasks([
      createTask({ id: "memory", kind: "memory_maintenance" }),
      createTask({ id: "subagent", kind: "subagent" }),
      createTask({ id: "schedule", kind: "schedule" }),
    ]);

    assert.deepEqual(groups.map((group) => group.kind), ["schedule", "subagent", "memory_maintenance"]);
  });
});

describe("RoleTasksPanel", () => {
  it("renders grouped status and only cancellable task actions", () => {
    const markup = renderToStaticMarkup(
      <RoleTasksPanel
        tasks={[
          createTask({ id: "schedule", kind: "schedule", status: "scheduled" }),
          createTask({ id: "memory", kind: "memory_maintenance", label: "记忆维护", status: "running", cancellable: false }),
        ]}
        cancellingTaskId="schedule"
        onCancel={() => undefined}
      />,
    );

    assert.match(markup, />计划任务</);
    assert.match(markup, />记忆维护</);
    assert.match(markup, />待执行</);
    assert.match(markup, />进行中</);
    assert.equal((markup.match(/>取消</g) ?? []).length, 1);
    assert.match(markup, /disabled=""/);
  });
});
