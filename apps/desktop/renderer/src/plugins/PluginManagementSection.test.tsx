import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";

let PluginManagementSection: typeof import("./PluginManagementSection").PluginManagementSection;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ PluginManagementSection } = await import("./PluginManagementSection"));
  await environment.cleanup();
});

describe("PluginManagementSection", () => {
  it("lists every discovered plugin and hot toggles one through plugins.setEnabled", async () => {
    const view = await mountTestComponent(null);
    const calls: Array<{ method: string; payload: Record<string, unknown> }> = [];
    let helloEnabled = true;
    Object.defineProperty(window, "miraDesktop", {
      configurable: true,
      value: {
        invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
          calls.push({ method, payload });
          if (method === "plugins.list") {
            return {
              id: "1", type: "response", method, error: null,
              payload: {
                plugins: [
                  { id: "hello", candidate_id: "builtin/hello", directory: "builtin/hello", source: "builtin", can_toggle: true, diagnostic: null, name: "hello", version: "0.1", description: "示例插件", enabled: helloEnabled, state: helloEnabled ? "ACTIVE" : "DISABLED", error: "", has_config_schema: false },
                ],
              },
            };
          }
          if (method === "plugins.setEnabled") {
            helloEnabled = payload.enabled as boolean;
            return { id: "1", type: "response", method, error: null, payload: { plugin_id: "hello", enabled: helloEnabled, generation: 2 } };
          }
          throw new Error(`unexpected method ${method}`);
        },
      },
    });

    try {
      await view.render(<PluginManagementSection />);
      assert.match(view.container.textContent ?? "", /hello/);
      assert.match(view.container.textContent ?? "", /ACTIVE/);

      const toggle = view.container.querySelector('button[role="switch"]') as HTMLButtonElement;
      assert.ok(toggle, "expected an enable switch to render");
      assert.equal(toggle.getAttribute("aria-checked"), "true");

      await act(async () => { toggle.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

      assert.ok(calls.some((call) => call.method === "plugins.setEnabled" && call.payload.enabled === false));
      assert.match(view.container.textContent ?? "", /DISABLED/);
    } finally {
      await view.cleanup();
    }
  });

  it("shows a load error with a retry action when plugins.list fails", async () => {
    const view = await mountTestComponent(null);
    Object.defineProperty(window, "miraDesktop", {
      configurable: true,
      value: { invoke: async () => { throw new Error("backend offline"); } },
    });

    try {
      await view.render(<PluginManagementSection />);
      assert.match(view.container.textContent ?? "", /backend offline/);
    } finally {
      await view.cleanup();
    }
  });
});


it("keeps the active switch and shows restart guidance after a refused hot toggle", async () => {
  const view = await mountTestComponent(null);
  const calls: string[] = [];
  Object.defineProperty(window, "miraDesktop", {
    configurable: true,
    value: { invoke: async ({ method }: { method: string }) => {
      calls.push(method);
      if (method === "plugins.list") return { id: "1", type: "response", method, error: null, payload: { plugins: [
        { id: "unsafe", candidate_id: "builtin/unsafe", directory: "builtin/unsafe", source: "builtin", can_toggle: true, diagnostic: null, name: "unsafe", version: "0.1", description: "", enabled: true, state: "ACTIVE", error: "", has_config_schema: false, supports_hot_unload: false },
      ] } };
      return { id: "2", type: "response", method, payload: {}, error: { code: "plugin_restart_required", message: "本次更改未保存；请退出应用后修改配置，再重新启动。", details: { plugin_ids: ["unsafe"], restart_required: true } } };
    } },
  });
  try {
    await view.render(<PluginManagementSection />);
    assert.match(view.container.textContent ?? "", /更改需重启/);
    const toggle = view.container.querySelector('button[role="switch"]') as HTMLButtonElement;
    await act(async () => { toggle.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /未保存.*重新启动/);
    assert.equal(toggle.getAttribute("aria-checked"), "true");
    assert.equal(toggle.disabled, false);
    assert.equal(calls.filter((method) => method === "plugins.list").length, 1);
  } finally {
    await view.cleanup();
  }
});

it("renders each conflicting directory and disables every unsafe candidate", async () => {
  const view = await mountTestComponent(null);
  const calls: string[] = [];
  const rows = ["CONFLICT", "CONFLICT", "UNTRUSTED", "BLOCKED"].map((state, index) => ({
    id: index < 2 ? "duplicate" : `plugin-${index}`, name: "same-name", version: "1.0.0",
    candidate_id: `candidate-${index}`, source: index === 0 ? "builtin" : "workspace",
    directory: `C:/plugins/root-${index}`, description: "", enabled: true, can_toggle: false,
    state, error: `diagnostic-${index}`, has_config_schema: false, supports_hot_unload: true,
    diagnostic: { code: state.toLowerCase(), stage: "discovery", field: "id", reason: `diagnostic-${index}`, path: "", state },
  }));
  Object.defineProperty(window, "miraDesktop", {
    configurable: true,
    value: { invoke: async ({ method }: { method: string }) => {
      calls.push(method);
      return { id: "1", type: "response", method, error: null, payload: { plugins: rows } };
    } },
  });
  try {
    await view.render(<PluginManagementSection />);
    const toggles = view.container.querySelectorAll<HTMLButtonElement>('button[role="switch"]');
    assert.equal(toggles.length, 4);
    for (const [index, toggle] of Array.from(toggles).entries()) {
      assert.equal(toggle.disabled, true);
      assert.equal(toggle.getAttribute("aria-checked"), "false");
      assert.ok(view.container.textContent?.includes(`C:/plugins/root-${index}`));
      assert.ok(view.container.textContent?.includes(`diagnostic-${index}`));
    }
    assert.ok(view.container.textContent?.includes("内置"));
    assert.ok(view.container.textContent?.includes("工作区"));
    assert.deepEqual(calls, ["plugins.list"]);
  } finally {
    await view.cleanup();
  }
});
