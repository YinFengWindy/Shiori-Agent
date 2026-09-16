import { renderToStaticMarkup } from "react-dom/server";
import { createElement, isValidElement, type ReactElement } from "react";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { applyPluginUiModules, type PluginUiModule } from "./pluginUiModuleContract.js";
import { PluginUiRegistry } from "./pluginUiRegistry.js";
import type { PluginRpcClient } from "./pluginBridgeClient.js";

/**
 * Invokes a function component directly and returns the React element it
 * produced, without mounting a DOM: a function component is just a
 * function, and JSX compiles to a plain `createElement` call, so `.props`
 * on the returned element is enough to inspect what was passed down.
 */
function renderElement<TProps>(
  Component: (props: TProps) => { type: unknown; props: Record<string, unknown> },
  props: TProps,
): { type: unknown; props: Record<string, unknown> } {
  let child: unknown;
  function Capture() {
    child = Component(props).props.children;
    return null;
  }
  renderToStaticMarkup(createElement(Capture));
  assert.ok(isValidElement(child), "plugin subtree must receive host services");
  return child as ReactElement<Record<string, unknown>>;
}

describe("applyPluginUiModules", () => {
  it("registers a schema-driven settings.section under the plugin's own id", () => {
    const registry = new PluginUiRegistry();
    const modules: Record<string, { default: PluginUiModule }> = {
      "/plugins/demo/ui/index.tsx": {
        default: { pluginId: "demo", settingsSection: { kind: "schema", label: "Demo" } },
      },
    };

    applyPluginUiModules(modules, registry);

    const entry = registry.getSettingsSection("demo");
    assert.ok(entry, "expected a settings.section entry for the demo plugin");
    assert.equal(entry?.kind, "standalone");
    assert.equal(entry?.pluginId, "demo");
    assert.equal(entry?.label, "Demo");
  });

  it("registers a custom-component settings.section and a nav.page from the same module", () => {
    const registry = new PluginUiRegistry();
    function CustomSection() { return null; }
    function NavPage() { return null; }
    const modules: Record<string, { default: PluginUiModule }> = {
      "/plugins/demo/ui/index.tsx": {
        default: {
          pluginId: "demo",
          settingsSection: { kind: "component", label: "Demo", component: CustomSection },
          navPage: { label: "Demo Page", component: NavPage },
        },
      },
    };

    applyPluginUiModules(modules, registry);

    // The registry entry now wraps the plugin's own component (issue #174
    // spec: plugin UI only uses an injected client, never window/IPC
    // directly), so the registered Component is no longer the plugin's bare
    // function reference — it is a binder that renders it with a client.
    const sectionComponent = registry.getSettingsSection("demo")?.Component;
    const navComponent = registry.getNavPage("demo")?.Component;
    assert.ok(sectionComponent, "expected a settings.section Component");
    assert.ok(navComponent, "expected a nav.page Component");
    assert.notEqual(sectionComponent, CustomSection);
    assert.notEqual(navComponent, NavPage);

    const sectionElement = renderElement(sectionComponent as never, { subsectionId: "default" });
    const navElement = renderElement(navComponent as never, { pageId: "demo" });
    assert.equal(sectionElement.type, CustomSection);
    assert.equal(navElement.type, NavPage);
  });

  it("injects into each component a client scoped to only its own plugin's RPC namespace", async () => {
    const registry = new PluginUiRegistry();
    function CustomSection() { return null; }
    function NavPage() { return null; }
    const modules: Record<string, { default: PluginUiModule }> = {
      "/plugins/demo/ui/index.tsx": {
        default: {
          pluginId: "demo",
          settingsSection: { kind: "component", label: "Demo", component: CustomSection },
          navPage: { label: "Demo Page", component: NavPage },
        },
      },
    };

    applyPluginUiModules(modules, registry);

    const sectionComponent = registry.getSettingsSection("demo")?.Component as never;
    const navComponent = registry.getNavPage("demo")?.Component as never;
    const sectionProps = renderElement(sectionComponent, { subsectionId: "default" }).props;
    const navProps = renderElement(navComponent, { pageId: "demo" }).props;

    // The base slot props (subsectionId/pageId) still pass through untouched...
    assert.equal(sectionProps.subsectionId, "default");
    assert.equal(navProps.pageId, "demo");

    // ...and both also received an injected `client`, without the plugin
    // module ever constructing one or naming itself.
    const sectionClient = sectionProps.client as PluginRpcClient;
    const navClient = navProps.client as PluginRpcClient;
    assert.equal(typeof sectionClient.call, "function");
    assert.equal(typeof navClient.call, "function");

    const calls: string[] = [];
    const originalWindow = (globalThis as { window?: unknown }).window;
    (globalThis as { window?: unknown }).window = {
      miraDesktop: {
        onEvent: () => () => {},
        invoke: async ({ method }: { method: string }) => {
          calls.push(method);
          return { id: "1", type: "response", method, error: null, payload: { generation: "g1" } };
        },
      },
    };
    try {
      await sectionClient.call("readSomething");
      await navClient.call("doSomething");
    } finally {
      (globalThis as { window?: unknown }).window = originalWindow;
    }

    // Every call the plugin makes — from either slot — is confined to
    // "plugin.demo.*"; the plugin never supplies (and cannot override) that
    // prefix itself.
    assert.deepEqual(calls, ["plugins.communication.open", "plugin.demo.readSomething", "plugins.communication.open", "plugin.demo.doSomething"]);
  });

  it("registers a nav.page's optional Sidebar bound with a client, and passes selectBlockedReason through untouched", () => {
    const registry = new PluginUiRegistry();
    function NavPage() { return null; }
    function Sidebar() { return null; }
    const selectBlockedReason = () => "not now";
    const modules: Record<string, { default: PluginUiModule }> = {
      "/plugins/demo/ui/index.tsx": {
        default: {
          pluginId: "demo",
          navPage: { label: "Demo Page", component: NavPage, sidebar: Sidebar, selectBlockedReason },
        },
      },
    };

    applyPluginUiModules(modules, registry);

    const entry = registry.getNavPage("demo");
    assert.ok(entry?.Sidebar, "expected a Sidebar on the nav.page entry");
    assert.notEqual(entry?.Sidebar, Sidebar, "Sidebar must be client-bound, not the bare component");
    // selectBlockedReason has no client/props to inject, so it is threaded through as-is.
    assert.equal(entry?.selectBlockedReason?.(), "not now");

    const sidebarElement = renderElement(entry!.Sidebar as never, {
      pageId: "demo",
      animating: false,
      collapsed: false,
      width: 280,
      onBeginResize: () => undefined,
    });
    assert.equal(sidebarElement.type, Sidebar);
    assert.equal(typeof (sidebarElement.props.client as PluginRpcClient).call, "function");
  });

  it("leaves Sidebar undefined and selectBlockedReason undefined when a nav.page doesn't declare them", () => {
    const registry = new PluginUiRegistry();
    function NavPage() { return null; }
    const modules: Record<string, { default: PluginUiModule }> = {
      "/plugins/demo/ui/index.tsx": {
        default: { pluginId: "demo", navPage: { label: "Demo Page", component: NavPage } },
      },
    };

    applyPluginUiModules(modules, registry);

    const entry = registry.getNavPage("demo");
    assert.equal(entry?.Sidebar, undefined);
    assert.equal(entry?.selectBlockedReason, undefined);
  });

  it("skips a malformed module instead of throwing", () => {
    const registry = new PluginUiRegistry();
    const modules = { "/plugins/broken/ui/index.tsx": { default: { settingsSection: {} } } } as unknown as Record<
      string, { default: PluginUiModule }
    >;

    assert.doesNotThrow(() => applyPluginUiModules(modules, registry));
    assert.equal(registry.listSettingsSections().length, 0);
  });
});
