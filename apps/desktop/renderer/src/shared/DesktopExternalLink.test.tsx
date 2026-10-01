import assert from "node:assert/strict";
import test from "node:test";
import { act } from "react";
import { mountTestComponent } from "@shiori/sdk/testing";
import { DesktopExternalLink } from "./DesktopExternalLink";

test("external links prevent renderer navigation and use the desktop shell", async () => {
  const view = await mountTestComponent(null);
  const opened: string[] = [];
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    openExternal: async (url: string) => { opened.push(url); return { ok: true, error: null }; },
  } });
  try {
    await view.render(<DesktopExternalLink href="mailto:3174898512@qq.com">联系作者</DesktopExternalLink>);
    const link = view.container.querySelector("a");
    assert.ok(link);
    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    await act(async () => { link.dispatchEvent(event); });
    assert.equal(event.defaultPrevented, true);
    assert.deepEqual(opened, ["mailto:3174898512@qq.com"]);
  } finally { await view.cleanup(); }
});

test("shell failures are visible and a successful retry clears the error", async () => {
  const view = await mountTestComponent(null);
  let calls = 0;
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    openExternal: async () => {
      calls += 1;
      if (calls === 1) throw new Error("无法启动邮件客户端");
      return { ok: true, error: null };
    },
  } });
  try {
    await view.render(<DesktopExternalLink href="mailto:3174898512@qq.com">联系作者</DesktopExternalLink>);
    const link = view.container.querySelector("a");
    assert.ok(link);
    await act(async () => link.click());
    assert.equal(view.container.querySelector('[role="alert"]')?.textContent, "无法启动邮件客户端");
    await act(async () => link.click());
    assert.equal(view.container.querySelector('[role="alert"]'), null);
  } finally { await view.cleanup(); }
});
