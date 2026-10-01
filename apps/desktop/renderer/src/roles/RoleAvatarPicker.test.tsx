import assert from "node:assert/strict";
import { act } from "react";
import { it } from "node:test";
import { mountTestComponent } from "@shiori/sdk/testing";
import { RoleAvatarPicker } from "./RoleAvatarPicker";

it("retains the avatar on cancellation and picker failure, and supports explicit removal", async () => {
  const view = await mountTestComponent(<div />);
  let picked: string[] = [];
  let rejected = false;
  let changed: string | undefined;
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    pickImages: async () => { if (rejected) throw new Error("无法读取图片"); return picked; },
    localAssetUrl: (path: string) => `https://local.test/${path}`,
  } });
  try {
    await view.render(<RoleAvatarPicker source="old.png" disabled={false} onChange={(value) => { changed = value; }} />);
    const picker = view.container.querySelector<HTMLButtonElement>('button[aria-label="更换头像"]')!;
    await act(async () => picker.click());
    assert.equal(changed, undefined);
    rejected = true;
    await act(async () => picker.click());
    assert.match(view.container.querySelector('[role="alert"]')!.textContent!, /无法读取图片/);
    assert.equal(changed, undefined);
    rejected = false;
    picked = ["new.png"];
    await act(async () => picker.click());
    assert.equal(changed, "new.png");
    await act(async () => view.container.querySelector<HTMLButtonElement>('button[aria-label="移除头像"]')!.click());
    assert.equal(changed, "");
  } finally { await view.cleanup(); }
});
