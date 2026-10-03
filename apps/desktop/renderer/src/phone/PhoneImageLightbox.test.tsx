import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";

let PhoneImageLightbox: typeof import("./PhoneImageLightbox").PhoneImageLightbox;
before(async () => {
  const view = await mountTestComponent(null);
  ({ PhoneImageLightbox } = await import("./PhoneImageLightbox"));
  await view.cleanup();
});

const windowGlobals = { miraDesktop: { localAssetUrl: (path: string) => `asset://${path}` } };

test("the enlarged picture is a labelled dialog that Escape, its close button and a click outside close", async () => {
  let closed = 0;
  const lightbox = (open: boolean) => (
    <PhoneImageLightbox imagePath="D:/media/cat.png" open={open} onClose={() => { closed += 1; }} />
  );
  const view = await mountTestComponent(lightbox(false), { windowGlobals });
  try {
    assert.equal(document.querySelector('[role="dialog"]'), null);
    await view.render(lightbox(true));
    const dialog = document.querySelector('[role="dialog"]');
    assert.equal(dialog?.getAttribute("aria-label"), "图片预览");
    assert.equal(dialog?.querySelector("img")?.getAttribute("src"), "asset://D:/media/cat.png");
    // Nothing but viewing: the close button is the only control.
    assert.deepEqual(Array.from(dialog?.querySelectorAll("button") ?? [], (button) => button.getAttribute("aria-label")), ["关闭图片预览"]);

    await act(async () => { dialog?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    assert.equal(closed, 1);
    await act(async () => dialog?.querySelector<HTMLButtonElement>("button")?.click());
    assert.equal(closed, 2);
    const backdrop = document.querySelector(".motion-backdrop");
    await act(async () => {
      backdrop?.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0 }));
      backdrop?.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: 0 }));
      backdrop?.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, button: 0 }));
      backdrop?.dispatchEvent(new MouseEvent("click", { bubbles: true, button: 0 }));
    });
    assert.equal(closed, 3);
  } finally { await view.cleanup(); }
});
