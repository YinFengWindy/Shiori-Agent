import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { NavPageEntry, PluginNavPageSidebarProps } from "../plugins/pluginUiRegistry";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { AppMainView } from "../shared/types";
import { SidebarTrackContent, type SidebarViewState } from "./SidebarTrackContent";

function sidebarState(overrides: Partial<SidebarViewState> = {}): SidebarViewState {
  return {
    collapsed: false,
    compact: false,
    width: 280,
    animating: false,
    resizing: false,
    onBeginResize: () => undefined,
    ...overrides,
  };
}

const baseProps = {
  settingsSection: "models",
  settingsSidebarSections: [],
  onOpenSettingsSection: () => undefined,
  roleWorkspaceViewActive: false,
  roleWorkspaceSection: "roles-list" as const,
  onOpenRoleWorkspaceSection: () => undefined,
  roles: [],
  activeRoleId: "",
  unreadCounts: {},
  bridgeReady: true,
  onOpenRole: () => undefined,
};

describe("SidebarTrackContent (issue #226 gap A)", () => {
  it("renders a plugin-page's own Sidebar into the track, wired to the host's resize handle, when the active nav page supplies one", async () => {
    const resizeCalls: unknown[] = [];
    const captured: { props: PluginNavPageSidebarProps | null } = { props: null };
    function DemoSidebar(props: PluginNavPageSidebarProps) {
      captured.props = props;
      return (
        <div data-testid="demo-plugin-sidebar">
          <button type="button" data-testid="demo-resize-handle" onPointerDown={props.onBeginResize as never} />
        </div>
      );
    }
    const entry: NavPageEntry = {
      slot: "nav.page", id: "demo", label: "Demo", pluginId: "demo", Component: () => null, Sidebar: DemoSidebar,
    };
    const mainView: AppMainView = { kind: "plugin-page", pageId: "demo" };
    const state = sidebarState({
      onBeginResize: (event) => { resizeCalls.push(event); },
    });

    const view = await mountTestComponent(
      <SidebarTrackContent
        {...baseProps}
        mainView={mainView}
        sidebarState={state}
        activePluginNavPage={entry}
      />,
    );
    try {
      const sidebarNode = view.container.querySelector('[data-testid="demo-plugin-sidebar"]');
      assert.ok(sidebarNode, "expected the plugin's Sidebar to render into the track");
      assert.equal(captured.props?.pageId, "demo");
      assert.equal(captured.props?.width, 280);
      assert.equal(captured.props?.collapsed, false);
      assert.equal(captured.props?.animating, false);

      const handle = view.container.querySelector('[data-testid="demo-resize-handle"]') as HTMLElement;
      handle.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
      assert.equal(resizeCalls.length, 1, "the Sidebar's onBeginResize must be the host's own handler");
    } finally {
      await view.cleanup();
    }
  });

  it("falls back to today's role-list sidebar when the active nav page supplies no Sidebar", async () => {
    const entry: NavPageEntry = {
      slot: "nav.page", id: "demo", label: "Demo", pluginId: "demo", Component: () => null,
    };
    const mainView: AppMainView = { kind: "plugin-page", pageId: "demo" };

    const view = await mountTestComponent(
      <SidebarTrackContent
        {...baseProps}
        mainView={mainView}
        sidebarState={sidebarState()}
        activePluginNavPage={entry}
      />,
    );
    try {
      assert.ok(view.container.querySelector('[data-testid="role-list"]'), "expected the RoleSidebar fallback");
      assert.equal(view.container.querySelector('[data-testid="demo-plugin-sidebar"]'), null);
    } finally {
      await view.cleanup();
    }
  });

  it("falls back to today's role-list sidebar for a plain chat view (no active plugin page at all)", async () => {
    const mainView: AppMainView = { kind: "chat" };
    const view = await mountTestComponent(
      <SidebarTrackContent
        {...baseProps}
        mainView={mainView}
        sidebarState={sidebarState()}
        activePluginNavPage={undefined}
      />,
    );
    try {
      assert.ok(view.container.querySelector('[data-testid="role-list"]'));
    } finally {
      await view.cleanup();
    }
  });

  it("still renders the role-workspace sidebar (unaffected by the new plugin-page branch)", async () => {
    const mainView: AppMainView = { kind: "roles-list" };
    const view = await mountTestComponent(
      <SidebarTrackContent
        {...baseProps}
        mainView={mainView}
        sidebarState={sidebarState()}
        roleWorkspaceViewActive
        activePluginNavPage={undefined}
      />,
    );
    try {
      assert.ok(view.container.querySelector(".role-workspace-sidebar"));
      assert.equal(view.container.querySelector('[data-testid="role-list"]'), null);
    } finally {
      await view.cleanup();
    }
  });
});
