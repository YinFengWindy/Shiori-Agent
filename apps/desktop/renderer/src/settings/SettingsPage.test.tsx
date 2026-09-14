import assert from "node:assert/strict";
import test from "node:test";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { SettingsPage } from "./SettingsPage";

test("the about route stays available while the backend is offline", async () => {
  const view = await mountTestComponent(null);
  let settingsReads = 0;
  Object.defineProperty(window, "miraDesktop", {
    configurable: true,
    value: {
      updates: {
        getState: async () => ({ revision: 0, currentVersion: "0.2.0", phase: "unsupported", latestVersion: null, progress: 0, error: null }),
        onState: () => () => undefined,
      },
      readSettings: async () => { settingsReads += 1; throw new Error("backend offline"); },
    },
  });
  try {
    await view.render(<SettingsPage bridgeReady={false} section="about" />);
    assert.match(view.container.textContent ?? "", /当前版本 v0.2.0/);
    assert.doesNotMatch(view.container.textContent ?? "", /开发模式/);
    assert.equal(view.container.querySelector("button")?.disabled, true);
    assert.equal(settingsReads, 0);
    const about = view.container.querySelector('[data-testid="about-settings"]');
    assert.ok(about?.closest('[data-testid="settings-page"]'));
    assert.equal(view.container.querySelectorAll(".settings-page").length, 1);
    assert.equal(view.container.querySelectorAll(".overflow-y-auto").length, 1);
  } finally { await view.cleanup(); }
});

test("the plugin route places every discovered row inside the settings scroll area without reading the shared draft", async () => {
  const view = await mountTestComponent(null);
  const calls: string[] = [];
  Object.defineProperty(window, "miraDesktop", {
    configurable: true,
    value: {
      invoke: async ({ method }: { method: string }) => {
        calls.push(method);
        assert.equal(method, "plugins.list");
        return {
          id: "1", type: "response", method, error: null,
          payload: {
            plugins: Array.from({ length: 16 }, (_, index) => ({
              id: `plugin-${index}`, name: `Plugin ${index}`, version: "0.1.0",
              description: "", enabled: true, state: "ACTIVE", error: "",
              has_config_schema: false,
            })),
          },
        };
      },
      readSettings: async () => { throw new Error("standalone route must not read the shared draft"); },
    },
  });
  try {
    await view.render(<SettingsPage bridgeReady={false} section="plugins" />);
    const page = view.container.querySelector('[data-testid="settings-page"]');
    assert.ok(page, "standalone routes need the host's bounded settings layout");
    const scrollArea = page.querySelector(".overflow-y-auto");
    assert.ok(scrollArea);
    assert.equal(scrollArea.querySelectorAll('[role="switch"]').length, 16);
    assert.ok(scrollArea.querySelector('[aria-label="启用 Plugin 15"]'));
    assert.deepEqual(calls, ["plugins.list"]);
  } finally { await view.cleanup(); }
});
