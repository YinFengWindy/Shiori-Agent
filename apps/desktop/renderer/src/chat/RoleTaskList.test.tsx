/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { RoleTask } from "../shared/types";
import { RoleTaskList } from "./RoleTaskList";

describe("RoleTaskList", () => {
  it("renders the plugin block first and only titles and one-line summaries of host tasks", () => {
    const task: RoleTask = {
      id: "task",
      role_id: "mira",
      kind: "subagent",
      status: "running",
      label: "整理资料",
      detail: "这是一段很长的任务说明",
      created_at: "2026-07-11T10:00:00+00:00",
      cancellable: true,
    };

    const markup = renderToStaticMarkup(
      <RoleTaskList tasks={[task]} block={<section>计划任务区块</section>} onSelect={() => undefined} />,
    );

    assert.ok(markup.indexOf("计划任务区块") < markup.indexOf(">后台任务<"));
    assert.match(markup, />记忆维护</);
    assert.equal((markup.match(/data-testid="role-task-group"/g) ?? []).length, 2);
    assert.match(markup, />这是一段很长的任务说明</);
    assert.doesNotMatch(markup, /2026-07-11/);
    assert.doesNotMatch(markup, />取消</);
  });
});
