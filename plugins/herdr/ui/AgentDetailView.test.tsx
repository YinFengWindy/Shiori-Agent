import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { AgentDetailView } from "./AgentDetailView";
import { herdrBackend, makeAgent, makeDetail, makeWorkspace } from "./testFixtures";
import type { AgentSummary } from "./types";

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function detailView(backend: ReturnType<typeof herdrBackend>, agent: AgentSummary) {
  return (
    <AgentDetailView
      paneId={agent.pane_id}
      listed={agent}
      listLoaded
      listError=""
      roleName={() => "Mira"}
      tasksConnected
      pollMs={5}
      client={backend.client}
      host={backend.fake.host}
    />
  );
}

test("an agent Herdr no longer knows is reported gone; unmounting stops the polling", async () => {
  const agent = makeAgent();
  const backend = herdrBackend([], [], [makeWorkspace("Shiori", [agent])]);
  const view = await mountTestComponent(detailView(backend, agent));
  try {
    await act(async () => wait(20));
    const header = view.container.querySelector('header[aria-label="Agent"]');
    assert.equal(header?.querySelector("h1")?.textContent, "herdr插件问题");
    assert.match(header?.textContent ?? "", /工作中.*Claude Code · D:\/Coding\/Shiori/);
    assert.equal(view.container.querySelector('[aria-label="终端输出"] pre')?.textContent, "output of wR:p2");
    // The list has not caught up yet; the agent's own read already says it is gone.
    backend.setWorkspaces([]);
    await act(async () => wait(30));
    assert.match(view.container.querySelector('[role="status"]')?.textContent ?? "", /Agent 已不存在/);
  } finally { await view.cleanup(); }
  const reads = backend.calls.length;
  await wait(30);
  assert.equal(backend.calls.length, reads, "no Herdr reads after the view is gone");
});

test("an agent carrying a task shows its Herdr header above the task's delivery and actions, around the agent's terminal", async () => {
  const agent = makeAgent({ pane_id: "w9:p1", workspace_id: "w9", agent: "codex", status: "idle", task_id: "task-a" });
  const backend = herdrBackend(
    [makeDetail({ status: "completed", summary: "改好了滚动", pr_url: "https://github.com/o/r/pull/1", can_cancel: false, output: "monitor output" })],
    [],
    [makeWorkspace("shiori-task", [agent])],
  );
  const view = await mountTestComponent(detailView(backend, agent));
  try {
    await act(async () => wait(10));
    assert.match(view.container.querySelector('header[aria-label="Agent"]')?.textContent ?? "", /herdr插件问题.*空闲.*Codex · D:\/Coding\/Shiori/);
    const task = view.container.querySelector('[aria-label="任务详情"]');
    assert.equal(task?.querySelector("h1")?.textContent, "修复滚动位置");
    assert.equal(view.container.querySelectorAll("h1").length, 1, "the task title is the only page heading");
    assert.match(task?.querySelector('[aria-label="修改摘要"]')?.textContent ?? "", /改好了滚动.*打开 Draft PR/);
    assert.equal(task?.querySelector('[aria-label="终端输出"] pre')?.textContent, "output of w9:p1");
    assert.ok(task?.querySelector('textarea[aria-label="追加要求"]'));
  } finally { await view.cleanup(); }
});
