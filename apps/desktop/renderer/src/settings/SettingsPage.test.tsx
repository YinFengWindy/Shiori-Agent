import assert from "node:assert/strict";
import test from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { SettingsPage } from "./SettingsPage";
import { useSettingsSubsectionMemory } from "./useSettingsSubsectionMemory";

/** No-op visibility/memory props for tests that don't exercise those concerns. */
const alwaysVisible = () => true;
const noopChangeSubsection = () => undefined;

const oneInstalledPlugin = [
  { id: "installed-demo", name: "Installed Demo", version: "0.1.0", description: "", enabled: true, state: "ACTIVE", error: "", has_config_schema: false, capabilities: [], channels: [] },
];

function stubPluginsListBridge(plugins: Array<Record<string, unknown>> = oneInstalledPlugin) {
  Object.defineProperty(window, "miraDesktop", {
    configurable: true,
    value: {
      onEvent: () => () => undefined,
      invoke: async ({ method }: { method: string }) => {
        assert.equal(method, "plugins.list");
        return { id: "1", type: "response", method, error: null, payload: { plugins } };
      },
    },
  });
}

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
    await view.render(
      <SettingsPage
        bridgeReady={false}
        section="about"
        isSectionVisible={alwaysVisible}
        isPluginEnabled={alwaysVisible}
        activeSubsections={{}}
        onChangeSubsection={noopChangeSubsection}
      />,
    );
    assert.match(view.container.textContent ?? "", /当前版本 v0.2.0/);
    assert.doesNotMatch(view.container.textContent ?? "", /开发模式/);
    assert.equal(view.container.querySelector("button")?.disabled, true);
    assert.equal(settingsReads, 0);
    const about = view.container.querySelector('[data-testid="about-settings"]');
    assert.ok(about?.closest('[data-testid="settings-page"]'));
    assert.equal(view.container.querySelectorAll(".settings-page").length, 1);
    assert.equal(view.container.querySelectorAll(".overflow-y-auto").length, 1);
    // Exactly one heading — proves SettingsPage's own wiring doesn't double
    // up with AboutSettingsPage; the heading's own spacing/markup rules are
    // AboutSettingsPage's and SettingsSubsectionNav's respective concerns,
    // tested in their own test files.
    assert.equal(Array.from(view.container.querySelectorAll("h2")).filter((h2) => h2.textContent === "关于").length, 1);
  } finally { await view.cleanup(); }
});

test("the plugin route places every discovered row inside the settings scroll area without reading the shared draft", async () => {
  const view = await mountTestComponent(null);
  const calls: string[] = [];
  Object.defineProperty(window, "miraDesktop", {
    configurable: true,
    value: {
      onEvent: () => () => undefined,
      invoke: async ({ method }: { method: string }) => {
        calls.push(method);
        assert.equal(method, "plugins.list");
        return {
          id: "1", type: "response", method, error: null,
          payload: {
            plugins: Array.from({ length: 16 }, (_, index) => ({
              id: `plugin-${index}`, name: `Plugin ${index}`, version: "0.1.0",
              description: "", enabled: true, state: "ACTIVE", error: "",
              has_config_schema: false, capabilities: [], channels: [],
            })),
          },
        };
      },
      readSettings: async () => { throw new Error("standalone route must not read the shared draft"); },
    },
  });
  try {
    await view.render(
      <SettingsPage
        bridgeReady={false}
        section="plugins"
        isSectionVisible={alwaysVisible}
        isPluginEnabled={alwaysVisible}
        activeSubsections={{}}
        onChangeSubsection={noopChangeSubsection}
      />,
    );
    const page = view.container.querySelector('[data-testid="settings-page"]');
    assert.ok(page, "standalone routes need the host's bounded settings layout");
    const scrollArea = page.querySelector(".overflow-y-auto");
    assert.ok(scrollArea);
    assert.equal(scrollArea.querySelectorAll('[role="switch"]').length, 16);
    assert.ok(scrollArea.querySelector('[aria-label="启用 Plugin 15"]'));
    assert.deepEqual(calls, ["plugins.list"]);
  } finally { await view.cleanup(); }
});

const pluginRow = (id: string, name: string) => ({
  id, name, version: "0.1.0", description: "", enabled: true, state: "ACTIVE", error: "", has_config_schema: true, capabilities: [], channels: [],
  candidate_id: `builtin/${id}`, can_toggle: true,
});

test("issue #230 AC 2 (restyle #362): a nested plugin page opens from its row's 「设置」, not from a tab, and returns to the list", async () => {
  pluginUiRegistry.registerSettingsSubsection({
    slot: "settings.subsection", parentId: "plugins", id: "novelai", label: "NovelAI",
    pluginId: "novelai", Component: () => <div data-testid="novelai-settings">NovelAI 配置</div>,
  });
  pluginUiRegistry.registerSettingsSubsection({
    slot: "settings.subsection", parentId: "plugins", id: "qqbot", label: "QQBot",
    pluginId: "qqbot", Component: () => <div data-testid="qqbot-settings">QQBot 配置</div>,
  });
  const view = await mountTestComponent(null);
  stubPluginsListBridge([pluginRow("novelai", "NovelAI"), pluginRow("qqbot", "QQBot"), { ...pluginRow("plain", "Plain"), has_config_schema: false }]);
  try {
    let selected: [string, string] | null = null;
    const render = (activeSubsections: Record<string, string>) => view.render(
      <SettingsPage
        bridgeReady={false}
        section="plugins"
        isSectionVisible={alwaysVisible}
        isPluginEnabled={alwaysVisible}
        activeSubsections={activeSubsections}
        onChangeSubsection={(sectionId, subsectionId) => { selected = [sectionId, subsectionId]; }}
      />,
    );

    await render({});
    assert.equal(view.container.querySelector('nav[aria-label="设置子区"]'), null, "plugin pages are not tabs beside 已安装");
    assert.ok(view.container.querySelector('[role="switch"]'), "default subsection (已安装) shows the plugin management list");
    const settingsButton = view.container.querySelector<HTMLButtonElement>('[aria-label="NovelAI 设置"]');
    assert.ok(settingsButton, "a plugin with a settings page gets a 设置 action on its row");
    assert.equal(view.container.querySelector('[aria-label="Plain 设置"]'), null);
    await act(async () => settingsButton.click());
    assert.deepEqual(selected, ["plugins", "novelai"]);

    await render({ plugins: "novelai" });
    assert.ok(view.container.querySelector('[data-testid="novelai-settings"]'), "expected the nested plugin's own component to render");
    assert.equal(view.container.querySelector('[data-testid="qqbot-settings"]'), null);
    assert.equal(view.container.querySelector("h2")?.textContent, "NovelAI");
    assert.equal(view.container.querySelectorAll(".settings-page").length, 1);
    assert.equal(view.container.querySelectorAll(".overflow-y-auto").length, 1);
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="返回插件"]')!.click());
    assert.deepEqual(selected, ["plugins", "list"]);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterSettingsSubsection("plugins", "novelai");
    pluginUiRegistry.unregisterSettingsSubsection("plugins", "qqbot");
  }
});

test("issue #230 AC 3: disabling the active plugin's subtab hides it and falls back to 已安装", async () => {
  pluginUiRegistry.registerSettingsSubsection({
    slot: "settings.subsection", parentId: "plugins", id: "demo", label: "Demo",
    pluginId: "demo", Component: () => <div data-testid="demo-settings">Demo 配置</div>,
  });
  const view = await mountTestComponent(null);
  stubPluginsListBridge();
  try {
    await view.render(
      <SettingsPage
        bridgeReady={false}
        section="plugins"
        isSectionVisible={alwaysVisible}
        activeSubsections={{ plugins: "demo" }}
        isPluginEnabled={() => false}
        onChangeSubsection={noopChangeSubsection}
      />,
    );
    const nav = view.container.querySelector('nav[aria-label="设置子区"]');
    // Only 已安装 remains once its owning plugin is disabled — no subtab nav
    // at all, since a single-subtab standalone section shows none (matches "about").
    assert.equal(nav, null);
    assert.equal(view.container.querySelector('[data-testid="demo-settings"]'), null);
    assert.ok(view.container.querySelector('[role="switch"]'), "expected the fallback 已安装 content to render instead");
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterSettingsSubsection("plugins", "demo");
  }
});

test("issue #230 AC 3 round trip: disabling then re-enabling the active plugin does not snap the page back to it", async () => {
  pluginUiRegistry.registerSettingsSubsection({
    slot: "settings.subsection", parentId: "plugins", id: "demo", label: "Demo",
    pluginId: "demo", Component: () => <div data-testid="demo-settings">Demo 配置</div>,
  });
  const view = await mountTestComponent(null);
  stubPluginsListBridge([pluginRow("demo", "Demo")]);

  // Uses the real memory hook (not a hand-fed prop object) so the
  // fallback-commit write-back under test actually runs: without it, the
  // record would keep remembering "demo" forever, and re-enabling the
  // plugin would silently jump the page back to its config tab.
  function Harness({ pluginEnabled }: { pluginEnabled: boolean }) {
    const memory = useSettingsSubsectionMemory();
    return (
      <SettingsPage
        bridgeReady={false}
        section="plugins"
        isSectionVisible={alwaysVisible}
        isPluginEnabled={() => pluginEnabled}
        activeSubsections={memory.activeSubsections}
        onChangeSubsection={memory.remember}
      />
    );
  }

  try {
    await view.render(<Harness pluginEnabled />);
    const demoSettings = view.container.querySelector<HTMLButtonElement>('[aria-label="Demo 设置"]')!;
    await act(async () => demoSettings.click());
    assert.ok(view.container.querySelector('[data-testid="demo-settings"]'), "expected to land on the demo page after opening it");

    // Disable: display falls back to 已安装, and the fix under test commits
    // that fallback into the record instead of leaving "demo" remembered.
    await view.render(<Harness pluginEnabled={false} />);
    assert.equal(view.container.querySelector('[data-testid="demo-settings"]'), null);
    assert.ok(view.container.querySelector('[role="switch"]'), "expected 已安装 to show while demo is disabled");

    // Re-enable: must stay on 已安装 — a stale remembered "demo" would jump
    // the page back to it with no click, out from under the user.
    await view.render(<Harness pluginEnabled />);
    assert.equal(view.container.querySelector('[data-testid="demo-settings"]'), null, "must not silently jump back to demo's tab");
    assert.ok(view.container.querySelector('[role="switch"]'), "expected to still be on 已安装 after re-enabling");
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterSettingsSubsection("plugins", "demo");
  }
});

