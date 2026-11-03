/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, createElement } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import {  useLeftSidebarState } from "./useLeftSidebarState";

// Shell values: nav rail 52px wide, sidebar 220..400 (default 220),
// collapse at half the minimum width.
const minWidth = 220;
const maxWidth = 400;
const collapseThreshold = 110;

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
