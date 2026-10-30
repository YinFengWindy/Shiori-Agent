/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { PluginRoleTasksProps } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { RoleTask } from "../shared/types";
import { roleTasksUiRegistry } from "../plugins/roleTasksUiRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";
import { RoleTasksPanel } from "./RoleTasksPanel";

const task: RoleTask = {
  id: "subagent",
  role_id: "mira",
  kind: "subagent",
  status: "running",
  label: "整理资料",
  detail: "整理今天的资料",
  created_at: "2026-07-11T10:00:00+00:00",
  cancellable: true,
};

/** Stands in for the schedule plugin's block: shows its view and opens one. */
function ScheduleBlock({ roleId, view, onViewChange }: PluginRoleTasksProps) {
  return <section>
    <span>{`计划任务区块:${roleId}:${view || "list"}`}</span>
    <button type="button" onClick={() => onViewChange(view ? "" : "create")}>{view ? "返回" : "新增"}</button>
  </section>;
}

function panel() {
  return <RoleTasksPanel roleId="mira" tasks={[task]} cancellingTaskId="" error="" onClearError={() => undefined} onCancel={async () => undefined} />;
}

async function withSchedule<T>(enabled: boolean, run: () => Promise<T> | T): Promise<T> {
  roleTasksUiRegistry.register({ pluginId: "schedule", Component: ScheduleBlock });
  setPluginEnabledSnapshot([{ id: "schedule", enabled, state: enabled ? "ACTIVE" : "DISABLED" }]);
  try {
    return await run();
  } finally {
    roleTasksUiRegistry.unregister("schedule");
    resetPluginEnabledStateForTests();
  }
}

function buttonNamed(container: HTMLElement, text: string) {
  return [...container.querySelectorAll("button")].find((button) => button.textContent === text);
}

describe("RoleTasksPanel", () => {
  it("lists the host's tasks without the block while the schedule plugin is off", async () => {
    const markup = await withSchedule(false, () => renderToStaticMarkup(panel()));

    assert.match(markup, />整理资料</);
    assert.doesNotMatch(markup, /计划任务区块/);
  });

  it("hands the whole panel to the block for its views and takes it back", async () => {
    await withSchedule(true, async () => {
      const view = await mountTestComponent(panel());
      try {
        const text = () => view.container.textContent ?? "";
        assert.match(text(), /计划任务区块:mira:list/);
        assert.match(text(), /整理资料/);

        await act(async () => buttonNamed(view.container, "新增")?.click());
        assert.match(text(), /计划任务区块:mira:create/);
        assert.doesNotMatch(text(), /整理资料/);

        await act(async () => buttonNamed(view.container, "返回")?.click());
        assert.match(text(), /计划任务区块:mira:list/);
        assert.match(text(), /整理资料/);
      } finally {
        await view.cleanup();
      }
    });
  });
});
