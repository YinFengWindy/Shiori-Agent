import assert from "node:assert/strict";
import test from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { SettingsSubsectionNav } from "./SettingsSubsectionNav";

test("renders the section label as a heading, with the header supplying the spacing under it", async () => {
  const view = await mountTestComponent(null);
  try {
    await view.render(
      <SettingsSubsectionNav label="插件" subsections={[{ id: "list", label: "已安装" }]} currentSubsectionId="list" onSelect={() => undefined} />,
    );
    const heading = view.container.querySelector("h2");
    assert.equal(heading?.textContent, "插件");
    const header = heading?.closest("header");
    assert.ok(header?.className.includes("mb-6"), "expected the header to own the 24px gap under the heading");
  } finally { await view.cleanup(); }
});

test("renders no subtab strip at all for a single subsection, matching a section with no plugin subtabs", async () => {
  const view = await mountTestComponent(null);
  try {
    await view.render(
      <SettingsSubsectionNav label="关于" subsections={[{ id: "updates", label: "应用更新" }]} currentSubsectionId="updates" onSelect={() => undefined} />,
    );
    assert.equal(view.container.querySelector('nav[aria-label="设置子区"]'), null);
  } finally { await view.cleanup(); }
});

test("renders one button per subsection with correct aria-current and a horizontally scrollable strip", async () => {
  const view = await mountTestComponent(null);
  try {
    await view.render(
      <SettingsSubsectionNav
        label="插件"
        subsections={[{ id: "list", label: "已安装" }, { id: "novelai", label: "NovelAI" }]}
        currentSubsectionId="novelai"
        onSelect={() => undefined}
      />,
    );
    const nav = view.container.querySelector('nav[aria-label="设置子区"]');
    assert.ok(nav, "expected the subtab strip once there is more than one subsection");
    assert.ok(nav.className.includes("overflow-x-auto"), "expected the strip to scroll horizontally when crowded");
    const buttons = Array.from(nav.querySelectorAll("button"));
    assert.deepEqual(buttons.map((button) => button.textContent), ["已安装", "NovelAI"]);
    assert.equal(buttons[0]?.getAttribute("aria-current"), null);
    assert.equal(buttons[1]?.getAttribute("aria-current"), "page");
  } finally { await view.cleanup(); }
});

test("calls onSelect with the clicked subsection's id", async () => {
  const view = await mountTestComponent(null);
  try {
    let selected: string | null = null;
    await view.render(
      <SettingsSubsectionNav
        label="插件"
        subsections={[{ id: "list", label: "已安装" }, { id: "novelai", label: "NovelAI" }]}
        currentSubsectionId="list"
        onSelect={(id) => { selected = id; }}
      />,
    );
    const novelaiButton = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "NovelAI")!;
    await act(async () => novelaiButton.click());
    assert.equal(selected, "novelai");
  } finally { await view.cleanup(); }
});
