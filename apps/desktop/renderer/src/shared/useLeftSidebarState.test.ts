/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, createElement } from "react";
import { mountTestComponent } from "./testing/domTestHarness";
import { resolveLeftSidebarDragUpdate, useLeftSidebarState } from "./useLeftSidebarState";

// Shell values: nav rail 52px wide, sidebar 220..400 (default 220),
// collapse at half the minimum width.
const minWidth = 220;
const maxWidth = 400;
const collapseThreshold = 110;
const navRailWidth = 52;

describe("resolveLeftSidebarDragUpdate", () => {
  it("does not move the sidebar when the pointer has not moved", () => {
    // The grab lands on the handle at the sidebar's right edge, which in
    // viewport coordinates is navRail + width — not width. Reading that
    // absolute position as the new width is what used to make the sidebar
    // jump right by the rail's width on the first pointer sample.
    const grabX = navRailWidth + 220;
    assert.deepEqual(
      resolveLeftSidebarDragUpdate(220, grabX, grabX, minWidth, maxWidth, collapseThreshold),
      { collapsed: false, width: 220 },
    );
  });

  it("tracks the pointer delta rather than its absolute position", () => {
    const grabX = navRailWidth + 220;
    assert.deepEqual(
      resolveLeftSidebarDragUpdate(220, grabX, grabX + 40, minWidth, maxWidth, collapseThreshold),
      { collapsed: false, width: 260 },
    );
    assert.deepEqual(
      resolveLeftSidebarDragUpdate(220, grabX, grabX - 60, minWidth, maxWidth, collapseThreshold),
      { collapsed: false, width: 220 },
    );
  });

  it("is unaffected by what sits to the left of the track", () => {
    // Same drag, different rail width: the resulting width must not change.
    const narrow = resolveLeftSidebarDragUpdate(220, 0 + 220, 220 + 30, minWidth, maxWidth, collapseThreshold);
    const wide = resolveLeftSidebarDragUpdate(220, 500 + 220, 720 + 30, minWidth, maxWidth, collapseThreshold);
    assert.deepEqual(narrow, wide);
    assert.deepEqual(narrow, { collapsed: false, width: 250 });
  });

  it("clamps to the supported range", () => {
    const grabX = navRailWidth + 220;
    assert.deepEqual(
      resolveLeftSidebarDragUpdate(220, grabX, grabX + 1000, minWidth, maxWidth, collapseThreshold),
      { collapsed: false, width: maxWidth },
    );
  });

  it("collapses once the dragged width falls below the threshold", () => {
    const grabX = navRailWidth + 220;
    // 220 - 111 = 109, below the 110 threshold.
    assert.deepEqual(
      resolveLeftSidebarDragUpdate(220, grabX, grabX - 111, minWidth, maxWidth, collapseThreshold),
      { collapsed: true, width: null },
    );
    // 220 - 109 = 111, still above it.
    assert.deepEqual(
      resolveLeftSidebarDragUpdate(220, grabX, grabX - 109, minWidth, maxWidth, collapseThreshold),
      { collapsed: false, width: minWidth },
    );
  });

  it("grows from zero when dragging a collapsed sidebar open", () => {
    // Collapsed: the rendered width is 0 and the handle sits at the rail's
    // right edge. Dragging right must follow the pointer from nothing, not
    // resume from the width the sidebar had before it was collapsed.
    assert.deepEqual(
      resolveLeftSidebarDragUpdate(0, navRailWidth, navRailWidth + 240, minWidth, maxWidth, collapseThreshold),
      { collapsed: false, width: 240 },
    );
    assert.deepEqual(
      resolveLeftSidebarDragUpdate(0, navRailWidth, navRailWidth + 40, minWidth, maxWidth, collapseThreshold),
      { collapsed: true, width: null },
    );
  });
});

type SidebarApi = ReturnType<typeof useLeftSidebarState>;

function SidebarHarness({ capture }: { capture: (api: SidebarApi) => void }) {
  capture(useLeftSidebarState({ minWidth, maxWidth, defaultWidth: 220, collapseThreshold, animationDurationMs: 0 }));
  return null;
}

async function mountSidebar(width: number) {
  let latest!: SidebarApi;
  const view = await mountTestComponent(createElement(SidebarHarness, { capture: (api: SidebarApi) => { latest = api; } }));
  const resize = async (next: number) => {
    await act(async () => {
      view.window.happyDOM.setViewport({ width: next });
      view.window.dispatchEvent(new view.window.Event("resize"));
    });
  };
  await resize(width);
  return { view, api: () => latest, resize };
}

describe("useLeftSidebarState", () => {
  it("keeps the toggle and the rendered state in step after a compact round trip", async () => {
    const { view, api, resize } = await mountSidebar(1920);
    try {
      assert.equal(api().collapsed, false);
      await resize(960);
      assert.equal(api().compact, true);
      assert.equal(api().collapsed, true);
      // The title-bar toggle reaches the drawer in compact mode.
      await act(async () => { api().toggle(); });
      assert.equal(api().collapsed, false);
      await resize(1920);
      assert.equal(api().compact, false);
      assert.equal(api().collapsed, false);
      // The first click after returning acts immediately.
      await act(async () => { api().toggle(); });
      assert.equal(api().collapsed, true);
    } finally { await view.cleanup(); }
  });

  it("closes the compact drawer on Escape and on navigation", async () => {
    const { view, api } = await mountSidebar(960);
    try {
      await act(async () => { api().toggle(); });
      assert.equal(api().collapsed, false);
      await act(async () => { view.window.dispatchEvent(new view.window.KeyboardEvent("keydown", { key: "Escape" })); });
      assert.equal(api().collapsed, true);
      await act(async () => { api().toggle(); });
      await act(async () => { api().dismissOverlay(); });
      assert.equal(api().collapsed, true);
    } finally { await view.cleanup(); }
  });

  it("reveals a collapsed wide sidebar for a workspace but not the compact drawer", async () => {
    const { view, api, resize } = await mountSidebar(1280);
    try {
      await act(async () => { api().toggle(); });
      await act(async () => { api().reveal(); });
      assert.equal(api().collapsed, false);
      await resize(960);
      await act(async () => { api().reveal(); });
      assert.equal(api().collapsed, true);
    } finally { await view.cleanup(); }
  });
});
