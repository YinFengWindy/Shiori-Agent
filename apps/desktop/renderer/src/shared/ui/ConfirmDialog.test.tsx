import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../testing/domTestHarness";

let ConfirmDialog: typeof import("./ConfirmDialog").ConfirmDialog;
before(async () => {
  const view = await mountTestComponent(null);
  ({ ConfirmDialog } = await import("./ConfirmDialog"));
  await view.cleanup();
});

test("confirmation exposes its title/description, content and explicit actions", async () => {
  let confirmed = 0;
  let cancelled = 0;
  const view = await mountTestComponent(<ConfirmDialog open title="安装插件" description="完整信任说明" confirmLabel="信任并安装" destructive={false} error="校验失败" onConfirm={() => { confirmed++; }} onClose={() => { cancelled++; }}>
    <span>demo · 2.0.0</span>
  </ConfirmDialog>);
  try {
    const dialog = document.querySelector('[role="dialog"]');
    assert.ok(dialog);
    assert.equal(document.getElementById(dialog.getAttribute("aria-labelledby")!)?.textContent, "安装插件");
    assert.equal(document.getElementById(dialog.getAttribute("aria-describedby")!)?.textContent, "完整信任说明");
    assert.match(dialog.textContent ?? "", /demo · 2.0.0/);
    assert.equal(dialog.querySelector('[role="alert"]')?.textContent, "校验失败");
    const buttons = dialog.querySelectorAll<HTMLButtonElement>("button");
    await act(async () => buttons[1].click());
    assert.equal(confirmed, 1);
    await act(async () => buttons[0].click());
    assert.equal(cancelled, 1);
  } finally { await view.cleanup(); }
});

test("busy confirmations disable both actions and refuse Escape dismissal", async () => {
  let cancelled = 0;
  let confirmed = 0;
  const view = await mountTestComponent(<ConfirmDialog open busy title="确认删除角色" description="不可撤销" confirmLabel="确认删除" onClose={() => { cancelled++; }} onConfirm={() => { confirmed++; }} />);
  try {
    const dialog = document.querySelector('[role="dialog"]')!;
    const buttons = dialog.querySelectorAll<HTMLButtonElement>("button");
    assert.equal(buttons[1].textContent, "删除中...");
    assert.ok(buttons[1].className.includes("bg-danger"));
    for (const button of Array.from(buttons)) assert.equal(button.disabled, true);
    await act(async () => {
      dialog.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      for (const button of Array.from(buttons)) button.click();
    });
    assert.equal(cancelled, 0);
    assert.equal(confirmed, 0);
  } finally { await view.cleanup(); }
});

test("closing keeps the last open copy on screen while the exit animation plays", async () => {
  const view = await mountTestComponent(<ConfirmDialog open title="确认删除角色" description="“Mira” 删除后会移除角色会话。" confirmLabel="确认删除" onClose={() => {}} onConfirm={() => {}} />);
  // happy-dom runs no CSS animations; hand Base UI one exit animation that
  // stays pending so the popup is still mounted in its ending state.
  let finishExit!: () => void;
  const exit = { finished: new Promise<void>((resolve) => { finishExit = resolve; }) };
  const elementPrototype = Object.getPrototypeOf(document.createElement("div")) as { getAnimations?: () => unknown[] };
  const originalGetAnimations = elementPrototype.getAnimations;
  elementPrototype.getAnimations = () => [exit];
  try {
    await view.render(<ConfirmDialog open={false} title="确认删除角色" description="" confirmLabel="确认删除" onClose={() => {}} onConfirm={() => {}} />);
    const dialog = document.querySelector("[role=\"dialog\"]");
    assert.ok(dialog, "the popup should still be mounted while its exit runs");
    assert.match(dialog.textContent ?? "", /Mira/);
  } finally {
    finishExit();
    elementPrototype.getAnimations = originalGetAnimations;
    await view.cleanup();
  }
});

test("吟风 leads a persona confirmation with her face and line, before the factual consequence", async () => {
  const { confirmPersonaLines } = await import("../mascot/mascotLines");
  const view = await mountTestComponent(<ConfirmDialog open title="确认删除角色" description="“Mira” 删除后会移除角色会话与相关素材。" confirmLabel="确认删除"
    persona={confirmPersonaLines.deleteRole} error="删除失败" onClose={() => {}} onConfirm={() => {}} />);
  try {
    const dialog = document.querySelector('[role="dialog"]')!;
    const lead = dialog.querySelector('[data-testid="confirm-persona"]');
    assert.equal(lead?.getAttribute("data-expression"), "sad");
    assert.equal(lead?.querySelector('[data-testid="mascot-face"]')?.getAttribute("data-size"), "lg");
    const text = dialog.textContent ?? "";
    assert.ok(text.indexOf(confirmPersonaLines.deleteRole.text) < text.indexOf("删除后会移除"), text);
    // The accessible description stays the facts, not her line.
    assert.equal(document.getElementById(dialog.getAttribute("aria-describedby")!)?.textContent, "“Mira” 删除后会移除角色会话与相关素材。");
    // She already fronts the dialog: its error block does not add her again.
    const error = dialog.querySelector('[role="alert"]');
    assert.equal(error?.textContent, "删除失败");
    assert.equal(error?.querySelector('[data-testid="mascot-face"]'), null);
    assert.equal(dialog.querySelectorAll('[data-testid="mascot-face"]').length, 1);
  } finally { await view.cleanup(); }
});

test("a confirmation without persona (plugin dialogs) or with the 看板娘 off stays plain", async () => {
  const { confirmPersonaLines } = await import("../mascot/mascotLines");
  const { appearancePrefsStorageKey } = await import("../appearancePrefs");
  const { resetAppearancePrefsCache } = await import("../useAppearancePrefs");
  const plain = await mountTestComponent(<ConfirmDialog open title="删除提示词" description="删除后无法恢复。" confirmLabel="删除" onClose={() => {}} onConfirm={() => {}} />);
  try {
    assert.equal(document.querySelector('[data-testid="confirm-persona"]'), null);
    assert.equal(document.querySelector('[data-testid="mascot-face"]'), null);
  } finally { await plain.cleanup(); }
  const off = await mountTestComponent(null);
  try {
    resetAppearancePrefsCache();
    window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: true, mascot: false }));
    await off.render(<ConfirmDialog open title="删除素材" description="删除后无法恢复。" confirmLabel="删除" persona={confirmPersonaLines.deleteAsset} onClose={() => {}} onConfirm={() => {}} />);
    assert.equal(document.querySelector('[data-testid="confirm-persona"]'), null);
    assert.doesNotMatch(document.querySelector('[role="dialog"]')?.textContent ?? "", /明明挺好看/);
  } finally { await off.cleanup(); resetAppearancePrefsCache(); }
});
