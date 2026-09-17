import assert from "node:assert/strict";
import test from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { SettingsPage } from "./SettingsPage";

const oneInstalledPlugin = [
  { id: "installed-demo", name: "Installed Demo", version: "0.1.0", description: "", enabled: true, state: "ACTIVE", error: "", has_config_schema: false },
];

function stubPluginsListBridge(plugins: Array<Record<string, unknown>> = oneInstalledPlugin) {
  Object.defineProperty(window, "miraDesktop", {
    configurable: true,
    value: {
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

test("issue #230 AC 2: 「插件」 shows 已安装 plus one subtab per nested plugin contribution, each rendering its own content", async () => {
  pluginUiRegistry.registerSettingsSubsection({
    slot: "settings.subsection", parentId: "plugins", id: "novelai", label: "NovelAI",
    pluginId: "novelai", Component: () => <div data-testid="novelai-settings">NovelAI 配置</div>,
  });
  pluginUiRegistry.registerSettingsSubsection({
    slot: "settings.subsection", parentId: "plugins", id: "qqbot", label: "QQBot",
    pluginId: "qqbot", Component: () => <div data-testid="qqbot-settings">QQBot 配置</div>,
  });
  const view = await mountTestComponent(null);
  stubPluginsListBridge();
  try {
    let selected: [string, string] | null = null;
    const render = (activeSubsections: Record<string, string>) => view.render(
      <SettingsPage
        bridgeReady={false}
        section="plugins"
        activeSubsections={activeSubsections}
        onChangeSubsection={(sectionId, subsectionId) => { selected = [sectionId, subsectionId]; }}
      />,
    );

    await render({});
    const nav = view.container.querySelector('nav[aria-label="设置子区"]');
    assert.ok(nav, "expected the shared subtab nav to render for a multi-subtab standalone section");
    assert.deepEqual(Array.from(nav.querySelectorAll("button")).map((button) => button.textContent), ["已安装", "NovelAI", "QQBot"]);
    assert.ok(view.container.querySelector('[role="switch"]'), "default subtab (已安装) shows the plugin management list");

    const novelaiTab = Array.from(nav.querySelectorAll("button")).find((button) => button.textContent === "NovelAI")!;
    await act(async () => novelaiTab.click());
    assert.deepEqual(selected, ["plugins", "novelai"]);

    await render({ plugins: "novelai" });
    assert.ok(view.container.querySelector('[data-testid="novelai-settings"]'), "expected the nested plugin's own component to render");
    assert.equal(view.container.querySelector('[data-testid="qqbot-settings"]'), null);
    assert.equal(view.container.querySelectorAll(".settings-page").length, 1);
    assert.equal(view.container.querySelectorAll(".overflow-y-auto").length, 1);
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
        activeSubsections={{ plugins: "demo" }}
        isPluginEnabled={() => false}
        onChangeSubsection={() => undefined}
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

test("the about route still renders exactly one heading through the shared subtab-nav header", async () => {
  const view = await mountTestComponent(null);
  Object.defineProperty(window, "miraDesktop", {
    configurable: true,
    value: {
      updates: {
        getState: async () => ({ revision: 0, currentVersion: "0.2.0", phase: "unsupported", latestVersion: null, progress: 0, error: null }),
        onState: () => () => undefined,
      },
    },
  });
  try {
    await view.render(<SettingsPage bridgeReady={false} section="about" />);
    const headings = Array.from(view.container.querySelectorAll("h2")).filter((h2) => h2.textContent === "关于");
    assert.equal(headings.length, 1);

    // The header (`SettingsSubsectionNav`) already supplies mb-6 under the
    // heading; the about page's own content must not stack an extra
    // margin-top on top of that (regression: it briefly did, giving 关于
    // more space under its title than every other section — issue #230
    // review). AboutSettingsPage's outer `data-testid="about-settings"`
    // wrapper carries no classes of its own, so the first real content
    // block is its first child.
    const header = headings[0]!.closest("header")!;
    const aboutRoot = header.nextElementSibling as HTMLElement;
    assert.equal(aboutRoot?.getAttribute("data-testid"), "about-settings");
    const content = aboutRoot.firstElementChild as HTMLElement;
    assert.ok(content, "expected the about page to render content after its header");
    assert.equal(content.className.includes("mt-8"), false, "about content must not add its own top margin");
  } finally { await view.cleanup(); }
});
