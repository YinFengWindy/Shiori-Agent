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
      onBeginCancel={() => undefined}
      onCancel={() => undefined}
      onDismissCancel={() => undefined}
    />,
  );
}

describe("RoleTaskDetails", () => {
  it("confirms cancelling a background task inline", () => {
    const task: RoleTask = {
      id: "subagent",
      role_id: "mira",
      kind: "subagent",
      status: "running",
      label: "整理资料",
      detail: "整理今天的资料",
      created_at: "",
      cancellable: true,
    };

    assert.match(renderDetails(task), />取消</);
    assert.match(renderDetails(task, true), />确认取消此任务？</);
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
      cancellable: false,
    });

    assert.doesNotMatch(markup, />取消</);
  });
});
