import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { SettingsSaveFeedback } from "./SettingsSaveFeedback";

test("saved-but-unrefreshed settings offer read-back without discarding queued edits", async () => {
  let reads = 0;
  let discards = 0;
  const view = await mountTestComponent(<SettingsSaveFeedback phase="refresh-error" message="设置已保存，但刷新失败" onRetry={() => { reads += 1; }} onReload={() => { discards += 1; }} />);
  try {
    assert.equal(view.container.querySelector('[aria-label="重试保存"]'), null);
    assert.equal(view.container.querySelector('[aria-label="放弃草稿并重新加载"]'), null);
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="重新加载"]')?.click());
    assert.equal(reads, 1);
    assert.equal(discards, 0);
  } finally { await view.cleanup(); }
});
