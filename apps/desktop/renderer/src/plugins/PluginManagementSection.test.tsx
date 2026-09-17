import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { resetPluginEnabledStateForTests } from "./pluginEnabledStateStore";

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
        onEvent: () => () => undefined,
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
      value: { onEvent: () => () => undefined, invoke: async () => { throw new Error("backend offline"); } },
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
    value: { onEvent: () => () => undefined, invoke: async ({ method }: { method: string }) => {
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
    value: { onEvent: () => () => undefined, invoke: async ({ method }: { method: string }) => {
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

it("requires explicit trust confirmation and then shows pending restart without stale trust errors", async () => {
  resetPluginEnabledStateForTests();
  const view = await mountTestComponent(null);
  const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  let trusted = false;
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    onEvent: () => () => undefined,
    invoke: async (request: { method: string; payload: Record<string, unknown> }) => {
      requests.push(request);
      if (request.method === "plugins.trust") trusted = true;
      return { id: "1", type: "response", method: request.method, error: null, payload: { plugins: [{
        id: "manual", name: "Manual", version: "1.0.0", candidate_id: "C:/workspace/plugins/manual", directory: "C:/workspace/plugins/manual", source: "workspace", description: "",
        state: "UNTRUSTED", enabled: true, can_toggle: false, can_trust: !trusted, trust_fingerprint: "fingerprint", trust_directory: "C:/workspace/plugins/manual", trust_pending_restart: trusted,
        error: "外部插件尚未获得信任", diagnostic: { code: "trust_required", stage: "trust", field: "source", reason: "外部插件尚未获得信任", path: "", state: "UNTRUSTED" }, has_config_schema: false, supports_hot_unload: true,
      }] } };
    },
  } });
  const button = (text: string) => {
    const found = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((element) => element.textContent === text);
    assert.ok(found, `missing button ${text}`);
    return found;
  };
  try {
    await view.render(<PluginManagementSection />);
    assert.equal(view.container.querySelector<HTMLButtonElement>('[role="switch"]')?.disabled, true);
    await act(async () => button("信任…").click());
    assert.ok(document.querySelector('[role="dialog"]')?.textContent?.includes("可读写文件、访问网络并执行代码"));
    await act(async () => button("取消").click());
    assert.equal(requests.filter((request) => request.method === "plugins.trust").length, 0);
    await act(async () => button("信任…").click());
    await act(async () => button("确认信任").click());
    assert.deepEqual(requests.find((request) => request.method === "plugins.trust")?.payload, { candidate_id: "C:/workspace/plugins/manual", fingerprint: "fingerprint" });
    assert.ok(view.container.textContent?.includes("待重启"));
    assert.ok(view.container.textContent?.includes("重启 Shiori 后加载"));
    assert.equal(view.container.textContent?.includes("尚未获得信任"), false);
    assert.equal(view.container.querySelector<HTMLButtonElement>('[role="switch"]')?.disabled, true);
  } finally { await view.cleanup(); resetPluginEnabledStateForTests(); }
});
