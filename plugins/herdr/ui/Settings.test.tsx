import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, chooseSelectOption, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { HerdrSettingsPage } from "./Settings";
import type { HerdrSettings, SessionListResponse } from "./types";

const stored = {
  executable: "herdr", session: "shiori", default_agent: "codex", codex_model: "", claude_model: "",
  cli_timeout_seconds: 45, task_timeout_seconds: 7200,
} satisfies HerdrSettings;

function mount(sessions: () => Promise<SessionListResponse>) {
  const fake = createFakeHostServices({ config: stored });
  const client = createFakePluginClient({ call: async <T,>(method: string) => {
    assert.equal(method, "sessions.list");
    return await sessions() as T;
  } });
  return { fake, view: mountTestComponent(<HerdrSettingsPage client={client} host={fake.host} subsectionId="herdr" onSelectSubsection={() => {}} />) };
}

function sessionTrigger() {
  return document.querySelector<HTMLElement>('[role="combobox"][aria-label="Session"]');
}

test("a session picked from Herdr's list is saved; a configured one Herdr does not list stays selected", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { fake, view: mounting } = mount(async () => ({ sessions: [{ name: "default", status: "running" }, { name: "smoke", status: "stopped" }] }));
  const view = await mounting;
  try {
    assert.equal(sessionTrigger()?.textContent, "shiori（未找到）");
    await chooseSelectOption("Session", "default（运行中）");
    await act(async () => t.mock.timers.tick(400));
    assert.deepEqual(fake.config(), { ...stored, session: "default" });
    assert.equal(sessionTrigger()?.textContent, "default（运行中）");
  } finally { await view.cleanup(); }
});

test("a failed session list shows the error and the other fields still save", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { fake, view: mounting } = mount(async () => { throw new Error("找不到可执行程序：herdr"); });
  const view = await mounting;
  try {
    assert.match(view.container.textContent ?? "", /读取 session 列表失败：找不到可执行程序：herdr/);
    assert.equal(sessionTrigger()?.textContent, "shiori");
    await changeInputValue(view.container.querySelector<HTMLInputElement>('[aria-label="Herdr 路径"]')!, "D:/tools/herdr.exe");
    await act(async () => t.mock.timers.tick(400));
    assert.deepEqual(fake.config(), { ...stored, executable: "D:/tools/herdr.exe" });
  } finally { await view.cleanup(); }
});
