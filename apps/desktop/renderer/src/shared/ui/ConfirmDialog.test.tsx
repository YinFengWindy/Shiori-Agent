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
