/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { RoleTask } from "../shared/types";
import { RoleTaskList } from "./RoleTaskList";

describe("RoleTaskList", () => {
  it("renders only task titles and one-line summaries", () => {
    const task: RoleTask = {
      id: "task",
      role_id: "mira",
      kind: "schedule",
      status: "scheduled",
      label: "提醒",
      detail: "这是一段很长的任务说明",
      created_at: "2026-07-11T10:00:00+00:00",
      next_run_at: "2026-07-11T11:00:00+00:00",
      cancellable: true,
      editable: true,
      schedule: { tier: "instant", trigger: "after", when: "1h", content: "喝水" },
    };

    const markup = renderToStaticMarkup(<RoleTaskList tasks={[task]} onCreate={() => undefined} onSelect={() => undefined} />);

    assert.match(markup, /aria-label="新增计划任务"/);
    assert.match(markup, /class="truncate font-semibold"/);
    assert.match(markup, />这是一段很长的任务说明</);
    assert.doesNotMatch(markup, /2026-07-11/);
    assert.doesNotMatch(markup, />取消</);
  });
});
