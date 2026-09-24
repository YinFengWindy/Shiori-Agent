import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { act } from "react";
import { changeInputValue, mountTestComponent } from "../shared/testing/domTestHarness";

let PluginSchemaSettingsSection: typeof import("./PluginSchemaSettingsSection").PluginSchemaSettingsSection;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ PluginSchemaSettingsSection } = await import("./PluginSchemaSettingsSection"));
  await environment.cleanup();
});

describe("PluginSchemaSettingsSection", () => {
  it("renders a field per schema property and autosaves an edit through plugin.config.set", async () => {
    const view = await mountTestComponent(null);
    const calls: Array<{ method: string; payload: Record<string, unknown> }> = [];
    let stored = { app_id: "", client_secret: "" };
    Object.defineProperty(window, "miraDesktop", {
      configurable: true,
      value: {
        invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
          calls.push({ method, payload });
          if (method === "plugin.config.get") {
            return {
              id: "1", type: "response", method, error: null,
              payload: {
                plugin_id: "demo",
                schema: {
                  title: "DemoConfig",
                  required: ["app_id"],
                  properties: {
                    app_id: { type: "string", title: "App ID" },
                    client_secret: { type: "string" },
                  },
                },
                values: stored,
              },
            };
          }
          if (method === "plugin.config.set") {
            stored = { ...stored, ...(payload.values as Record<string, unknown>) };
            return { id: "1", type: "response", method, error: null, payload: { plugin_id: "demo", values: stored, generation: 2 } };
          }
          throw new Error(`unexpected method ${method}`);
        },
      },
    });

    try {
      await view.render(<PluginSchemaSettingsSection pluginId="demo" />);
      assert.match(view.container.textContent ?? "", /App ID/);
      const input = view.container.querySelector("input") as HTMLInputElement;
      assert.ok(input, "expected the App ID input to render");
      await changeInputValue(input, "app-123");

      assert.ok(calls.some((call) => call.method === "plugin.config.set" && call.payload.values && (call.payload.values as Record<string, unknown>).app_id === "app-123"));
    } finally {
      await view.cleanup();
    }
  });

  it("resyncs a JSON field's textarea when reloadConfig replaces the draft, not just on first mount", async () => {
    const view = await mountTestComponent(null);
    let stored: Record<string, unknown> = { tags: ["initial"] };
    let nextSetFails = false;
    Object.defineProperty(window, "miraDesktop", {
      configurable: true,
      value: {
        invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
          if (method === "plugin.config.get") {
            return {
              id: "1", type: "response", method, error: null,
              payload: {
                plugin_id: "demo",
                schema: { title: "DemoConfig", properties: { tags: { type: "array" } } },
                values: stored,
              },
            };
          }
          if (method === "plugin.config.set") {
            if (nextSetFails) {
              return {
                id: "1", type: "response", method,
                error: { code: "plugin_config_invalid", message: "保存失败" }, payload: null,
              };
            }
            stored = { ...stored, ...(payload.values as Record<string, unknown>) };
            return { id: "1", type: "response", method, error: null, payload: { plugin_id: "demo", values: stored, generation: 2 } };
          }
          throw new Error(`unexpected method ${method}`);
        },
      },
    });

    try {
      await view.render(<PluginSchemaSettingsSection pluginId="demo" />);
      const textarea = view.container.querySelector("textarea") as HTMLTextAreaElement;
      assert.ok(textarea, "expected a JSON textarea for the array field");
      assert.match(textarea.value, /initial/);

      // Edit locally, but make the save fail so the reload affordance shows
      // up, and the reloaded server value differs from this local edit.
      nextSetFails = true;
      await changeInputValue(textarea, JSON.stringify({ tags: ["unsaved-local-edit"] }));
      assert.match(textarea.value, /unsaved-local-edit/, "the field must still reflect the user's own typing");

      stored = { tags: ["reloaded-from-server"] };
      const reloadButton = view.container.querySelector('button[aria-label="放弃草稿并重新加载"]') as HTMLButtonElement;
      assert.ok(reloadButton, "expected a reload action once the save failed");
      await act(async () => { reloadButton.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

      // Before the fix this textarea kept showing "unsaved-local-edit"
      // forever: its text state was seeded once from `useState(() => ...)`
      // and never resynced when the `value` prop changed underneath it.
      assert.match(textarea.value, /reloaded-from-server/);
      assert.doesNotMatch(textarea.value, /unsaved-local-edit/);
    } finally {
      await view.cleanup();
    }
  });

  it("edits a list of strings as chips, shows number units, and folds raw-JSON fields under 高级", async () => {
    const view = await mountTestComponent(null);
    let stored: Record<string, unknown> = { allow_from: ["alice"], timeout_seconds: 30, groups: [] };
    Object.defineProperty(window, "miraDesktop", {
      configurable: true,
      value: {
        invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
          if (method === "plugin.config.get") {
            return {
              id: "1", type: "response", method, error: null,
              payload: {
                plugin_id: "demo",
                schema: { properties: {
                  allow_from: { type: "array", items: { type: "string" }, title: "允许的用户" },
                  timeout_seconds: { type: "integer", title: "超时", unit: "秒" },
                  groups: { type: "array", items: { type: "object" }, title: "群聊（旧版）" },
                } },
                values: stored,
              },
            };
          }
          stored = { ...stored, ...(payload.values as Record<string, unknown>) };
          return { id: "1", type: "response", method, error: null, payload: { plugin_id: "demo", values: stored, generation: 2 } };
        },
      },
    });

    try {
      await view.render(<PluginSchemaSettingsSection pluginId="demo" />);
      const text = view.container.textContent ?? "";
      assert.match(text, /允许的用户/);
      assert.doesNotMatch(text, /allow_from|Allow From/);
      assert.match(text, /秒/);
      assert.equal(view.container.querySelectorAll("textarea").length, 1, "only the object list stays a raw JSON editor");
      assert.equal(view.container.querySelector('[aria-expanded="false"]')?.textContent, "高级");

      const input = view.container.querySelector<HTMLInputElement>('input[aria-label="输入允许的用户"]')!;
      await changeInputValue(input, "bob");
      await act(async () => { input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
      assert.deepEqual(stored.allow_from, ["alice", "bob"]);

      await act(async () => view.container.querySelector<HTMLButtonElement>('button[aria-label="移除 alice"]')!.click());
      assert.deepEqual(stored.allow_from, ["bob"]);
    } finally {
      await view.cleanup();
    }
  });

  it("shows an unexpanded ${ENV} secret as the reference, not as masked dots, and lets a literal replace it", async () => {
    const view = await mountTestComponent(null);
    let stored: Record<string, unknown> = { token: "${NOVELAI_TOKEN}" };
    Object.defineProperty(window, "miraDesktop", {
      configurable: true,
      value: {
        invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
          if (method === "plugin.config.get") {
            return { id: "1", type: "response", method, error: null, payload: {
              plugin_id: "demo", schema: { properties: { token: { type: "string", title: "API Token" } } }, values: stored,
            } };
          }
          stored = { ...stored, ...(payload.values as Record<string, unknown>) };
          return { id: "1", type: "response", method, error: null, payload: { plugin_id: "demo", values: stored, generation: 2 } };
        },
      },
    });

    try {
      await view.render(<PluginSchemaSettingsSection pluginId="demo" />);
      assert.match(view.container.textContent ?? "", /引用环境变量 NOVELAI_TOKEN/);
      assert.match(view.container.textContent ?? "", /未设置/);
      assert.equal(view.container.querySelector('input[type="password"]'), null, "a reference must not look like a filled-in secret");

      const replace = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "改为直接填写")!;
      await act(async () => replace.click());
      const input = view.container.querySelector<HTMLInputElement>('input[aria-label="API Token"]')!;
      assert.equal(input.value, "");
      assert.equal(stored.token, "${NOVELAI_TOKEN}", "opening the input alone keeps the reference");
      await changeInputValue(input, "pst-literal");
      assert.equal(stored.token, "pst-literal");
    } finally {
      await view.cleanup();
    }
  });

  it("shows a load error with a retry action when plugin.config.get fails", async () => {
    const view = await mountTestComponent(null);
    Object.defineProperty(window, "miraDesktop", {
      configurable: true,
      value: {
        invoke: async () => { throw new Error("backend offline"); },
      },
    });

    try {
      await view.render(<PluginSchemaSettingsSection pluginId="demo" />);
      assert.match(view.container.textContent ?? "", /backend offline/);
    } finally {
      await view.cleanup();
    }
  });
});
