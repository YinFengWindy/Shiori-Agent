/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  initialSidebarLayout,
  isCompactShellWidth,
  isSidebarCollapsed,
  reduceSidebarLayout,
  type SidebarLayoutAction,
  type SidebarLayoutState,
} from "./sidebarLayout.js";

function run(state: SidebarLayoutState, ...actions: SidebarLayoutAction[]): SidebarLayoutState {
  return actions.reduce(reduceSidebarLayout, state);
}

const wide = initialSidebarLayout(1280);
const compact = initialSidebarLayout(960);

describe("sidebar layout model", () => {
  it("starts open on a wide window and closed-as-drawer on a compact one", () => {
    assert.equal(isCompactShellWidth(1023), true);
    assert.equal(isCompactShellWidth(1024), false);
    assert.equal(isSidebarCollapsed(wide), false);
    assert.equal(isSidebarCollapsed(compact), true);
  });

  it("toggles the preference on a wide window: the first click always acts", () => {
    const collapsed = run(wide, { type: "toggle" });
    assert.equal(isSidebarCollapsed(collapsed), true);
    assert.equal(isSidebarCollapsed(run(collapsed, { type: "toggle" })), false);
  });

  it("opens and closes the overlay drawer on a compact window without touching the preference", () => {
    const opened = run(compact, { type: "toggle" });
    assert.equal(isSidebarCollapsed(opened), false);
    assert.equal(opened.preferredCollapsed, false);
    assert.equal(isSidebarCollapsed(run(opened, { type: "toggle" })), true);
    assert.equal(isSidebarCollapsed(run(opened, { type: "dismiss-overlay" })), true);
  });

  it("does not carry a small-window collapse back to a large window", () => {
    // 1920 open → shrink to 960 (drawer closed) → grow back to 1920.
    const shrunk = run(wide, { type: "set-compact", compact: true });
    assert.equal(isSidebarCollapsed(shrunk), true);
    const regrown = run(shrunk, { type: "set-compact", compact: false });
    assert.equal(isSidebarCollapsed(regrown), false);
  });

  it("keeps an explicit wide-window collapse across a compact round trip", () => {
    const state = run(wide, { type: "toggle" }, { type: "set-compact", compact: true }, { type: "toggle" }, { type: "set-compact", compact: false });
    assert.equal(isSidebarCollapsed(state), true);
  });

  it("closes an open drawer when the window crosses the breakpoint", () => {
    const state = run(compact, { type: "toggle" }, { type: "set-compact", compact: false }, { type: "set-compact", compact: true });
    assert.equal(state.overlayOpen, false);
  });

  it("reveals a workspace sidebar on wide windows only", () => {
    assert.equal(isSidebarCollapsed(run(wide, { type: "toggle" }, { type: "reveal" })), false);
    assert.equal(isSidebarCollapsed(run(compact, { type: "reveal" })), true);
  });

  it("maps a drag to the mode it happens in", () => {
    assert.equal(run(wide, { type: "drag", collapsed: true }).preferredCollapsed, true);
    const dragged = run(compact, { type: "drag", collapsed: false });
    assert.equal(dragged.overlayOpen, true);
    assert.equal(dragged.preferredCollapsed, false);
  });

  it("returns the same state object when nothing changes", () => {
    assert.equal(reduceSidebarLayout(wide, { type: "reveal" }), wide);
    assert.equal(reduceSidebarLayout(wide, { type: "set-compact", compact: false }), wide);
    assert.equal(reduceSidebarLayout(wide, { type: "dismiss-overlay" }), wide);
    assert.equal(reduceSidebarLayout(wide, { type: "drag", collapsed: false }), wide);
  });
});
