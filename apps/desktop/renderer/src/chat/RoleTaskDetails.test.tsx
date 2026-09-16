/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { RoleTask } from "../shared/types";
import { RoleTaskDetails } from "./RoleTaskDetails";

function renderDetails(task: RoleTask, confirmingCancel = false) {
  return renderToStaticMarkup(
    <RoleTaskDetails
      task={task}
      cancelling={false}
      error=""
      confirmingCancel={confirmingCancel}
      onBack={() => undefined}
      onEdit={() => undefined}
      onBeginCancel={() => undefined}
      onCancel={() => undefined}
      onDismissCancel={() => undefined}
    />,
  );
}

describe("RoleTaskDetails", () => {
  it("shows complete schedule information and supported actions", () => {
    const markup = renderDetails({
      id: "schedule",
      role_id: "mira",
      kind: "schedule",
      status: "scheduled",
      label: "天气",
      detail: "查询今天的天气",
      created_at: "2026-07-11T10:00:00+00:00",
      next_run_at: "2026-07-12T01:00:00+00:00",
      cancellable: true,
      editable: true,
      schedule: { tier: "soft", trigger: "every", when: "0 9 * * *", content: "查询今天的天气" },
    });

    assert.match(markup, />AI 生成</);
    assert.match(markup, />循环执行</);
    assert.match(markup, />0 9 \* \* \*</);
    assert.match(markup, />编辑</);
    assert.match(markup, />取消</);
  });

  it("disables editing while running and confirms destructive actions inline", () => {
    const markup = renderDetails({
      id: "schedule",
      role_id: "mira",
      kind: "schedule",
      status: "running",
      label: "天气",
      detail: "查询天气",
      created_at: "",
      next_run_at: "",
      cancellable: true,
      editable: false,
      schedule: { tier: "soft", trigger: "after", when: "1h", content: "查询天气" },
    }, true);

    assert.match(markup, />任务运行期间不可编辑</);
    assert.match(markup, />确认取消此任务？</);
    assert.match(markup, />确认取消</);
  });

  it("keeps memory maintenance read-only", () => {
    const markup = renderDetails({
      id: "memory",
      role_id: "mira",
      kind: "memory_maintenance",
      status: "running",
      label: "记忆维护",
      detail: "整理角色记忆",
      created_at: "",
      next_run_at: "",
      cancellable: false,
      editable: false,
      schedule: null,
    });

    assert.doesNotMatch(markup, />编辑</);
    assert.doesNotMatch(markup, />取消</);
  });
});
