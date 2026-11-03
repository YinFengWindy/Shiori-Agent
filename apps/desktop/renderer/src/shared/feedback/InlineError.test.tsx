import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act, type ReactElement } from "react";
import { appearancePrefsStorageKey } from "../appearancePrefs";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { resetAppearancePrefsCache } from "../useAppearancePrefs";
import { InlineError } from "./InlineError";

afterEach(() => resetAppearancePrefsCache());

/** Mounts `element` with 设置 › 外观 › 看板娘 set to `mascot`. */
async function mount(element: ReactElement, mascot = true) {
  const view = await mountTestComponent(null);
  resetAppearancePrefsCache();
  window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: true, mascot }));
  await view.render(element);
  return view;
}

const block = (container: HTMLElement) => container.querySelector('[role="alert"], [role="status"]');

describe("InlineError", () => {

  it("announces a requested result politely with role status", async () => {
    const view = await mount(<InlineError role="status" persona="connectionTestFailed" message="401" />);
    try {
      assert.equal(block(view.container)?.getAttribute("role"), "status");
    } finally { await view.cleanup(); }
  });
});

it("keeps diagnostics folded and scrubbed when passed separately from the summary", async () => {
  const view = await mount(<InlineError persona={false} message="本地服务处理失败" detail="OSError: token=private-value" />);
  try {
    assert.match(view.container.textContent ?? "", /本地服务处理失败/);
    assert.doesNotMatch(view.container.textContent ?? "", /OSError|private-value/);
    await act(async () => view.container.querySelector("button")?.click());
    assert.match(view.container.textContent ?? "", /OSError/);
    assert.doesNotMatch(view.container.textContent ?? "", /private-value/);
  } finally { await view.cleanup(); }
});
