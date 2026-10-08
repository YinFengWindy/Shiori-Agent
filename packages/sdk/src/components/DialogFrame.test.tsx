import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { mountTestComponent } from "../testing/index";
import { DialogFrame } from "./DialogFrame";

// The test DOM has no Tailwind build. These are the three rules that decide a
// kept-mounted popup's display in the renderer, in the order Tailwind emits
// them (preflight first, utilities after; the generated selector was checked
// against the real renderer build).
const tailwindRules = `
[hidden] { display: none; }
.flex { display: flex; }
.\\[\\&\\[hidden\\]\\]\\:hidden[hidden] { display: none; }
`;

async function settle() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
}

test("a kept-mounted popup is not displayed once closed, despite its flex layout", async () => {
  const frame = (open: boolean) => <Dialog.Root open={open}><DialogFrame title="主动推送" closeLabel="关闭" keepMounted><p>内容</p></DialogFrame></Dialog.Root>;
  const view = await mountTestComponent(frame(true));
  const style = document.createElement("style");
  style.textContent = tailwindRules;
  document.head.append(style);
  try {
    await settle();
    const popup = document.querySelector<HTMLElement>('[role="dialog"]')!;
    assert.equal(window.getComputedStyle(popup).display, "flex");
    await view.render(frame(false));
    await settle();
    assert.equal(popup.isConnected, true, "kept mounted");
    assert.equal(popup.hidden, true);
    assert.equal(window.getComputedStyle(popup).display, "none");
    // The backdrop sets no display of its own, so preflight's [hidden] rule covers it.
    const backdrop = document.querySelector<HTMLElement>(".motion-backdrop");
    assert.ok(!backdrop || window.getComputedStyle(backdrop).display === "none");
  } finally { await view.cleanup(); style.remove(); }
});
