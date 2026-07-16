/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { RoleTask } from "../shared/types";
import { RoleTasksPanel } from "./RoleTasksPanel";

const task: RoleTask = {
  id: "schedule",
  role_id: "mira",
  kind: "schedule",
  status: "scheduled",
  label: "喝水提醒",
  detail: "每隔一小时提醒喝水",
  created_at: "2026-07-11T10:00:00+00:00",
  next_run_at: "2026-07-11T11:00:00+00:00",
  cancellable: true,
  editable: true,
  schedule: { tier: "instant", trigger: "every", when: "1h", content: "喝水", timezone: "Asia/Shanghai" },
};

describe("RoleTasksPanel", () => {
  it("starts on the lightweight task directory", () => {
    const markup = renderToStaticMarkup(
      <RoleTasksPanel
        tasks={[task]}
        operation={null}
        error=""
        onClearError={() => undefined}
        onCreate={async () => task}
        onUpdate={async () => task}
        onCancel={async () => undefined}
      />,
    );

    assert.match(markup, />计划任务</);
    assert.match(markup, />喝水提醒</);
    assert.match(markup, />每隔一小时提醒喝水</);
    assert.doesNotMatch(markup, />待执行</);
    assert.doesNotMatch(markup, />取消</);
  });
});
