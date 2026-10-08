import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../testing/index";
import { CapabilitySettingsDialog } from "./CapabilitySettingsDialog";

function dialog() {
  return document.querySelector<HTMLElement>('[role="dialog"]');
}

async function settle() {
  // Base UI moves focus and finishes its open/close transition on later frames.
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
}

test("the ⚙ opens a dialog titled by the capability whose content mounts only while open", async () => {
  const view = await mountTestComponent(<CapabilitySettingsDialog title="主动推送"><label>推送策略<input /></label></CapabilitySettingsDialog>);
  try {
    assert.equal(dialog(), null);
    assert.equal(document.querySelector("input"), null);
    const trigger = view.container.querySelector<HTMLButtonElement>('button[aria-label="主动推送设置"]');
    assert.ok(trigger);
    await act(async () => trigger.click());
    await settle();
    const opened = dialog();
    assert.ok(opened);
    assert.equal(document.getElementById(opened.getAttribute("aria-labelledby")!)?.textContent, "主动推送");
    assert.ok(opened.querySelector("input"));

    await act(async () => opened.querySelector<HTMLButtonElement>('button[aria-label="关闭"]')!.click());
    await settle();
    assert.equal(dialog(), null);
    assert.equal(document.querySelector("input"), null);
  } finally { await view.cleanup(); }
});

test("focus moves into the dialog, Escape closes it and focus returns to the ⚙", async () => {
  const view = await mountTestComponent(<CapabilitySettingsDialog title="桌宠"><input aria-label="字段" /></CapabilitySettingsDialog>);
  try {
    const trigger = view.container.querySelector<HTMLButtonElement>('button[aria-label="桌宠设置"]')!;
    trigger.focus();
    await act(async () => trigger.click());
    await settle();
    const opened = dialog()!;
    assert.ok(opened.contains(document.activeElement), "focus is inside the dialog");

    await act(async () => {
      document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    await settle();
    assert.equal(dialog(), null);
    assert.equal(document.activeElement, trigger);
  } finally { await view.cleanup(); }
});

test("a long body scrolls inside a height-capped dialog while the title row stays", async () => {
  const view = await mountTestComponent(<CapabilitySettingsDialog title="主动推送">{Array.from({ length: 40 }, (_, index) => <p key={index}>行 {index}</p>)}</CapabilitySettingsDialog>);
  try {
    await act(async () => view.container.querySelector<HTMLButtonElement>("button")!.click());
    await settle();
    const opened = dialog()!;
    assert.match(opened.className, /max-h-\[calc\(100dvh-2rem\)\]/);
    assert.match(opened.className, /flex-col/);
    const body = opened.querySelector<HTMLElement>("[data-capability-settings-body]")!;
    assert.match(body.className, /overflow-y-auto/);
    assert.match(body.className, /min-h-0/);
    assert.equal(body.querySelectorAll("p").length, 40);
    // The title and close button sit outside the scrolling body.
    assert.equal(body.contains(document.getElementById(opened.getAttribute("aria-labelledby")!)), false);
    assert.equal(body.querySelector('button[aria-label="关闭"]'), null);
  } finally { await view.cleanup(); }
});
