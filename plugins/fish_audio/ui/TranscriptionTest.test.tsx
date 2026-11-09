import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { TranscriptionTest } from "./TranscriptionTest";

test("canceling file selection uploads nothing; failures preserve the previous transcript", async () => {
  let select = false; let fail = false; let uploads = 0;
  const { host } = createFakeHostServices({ pickFiles: async () => select ? ["staged.wav"] : [] });
  const client = createFakePluginClient({ call: async <T,>() => {
    uploads++; if (fail) throw new Error("账户额度不足"); return { text: "识别成功" } as T;
  } });
  const view = await mountTestComponent(<TranscriptionTest client={client} host={host} />);
  try {
    const click = () => act(async () => view.container.querySelector("button")!.click());
    await click(); assert.equal(uploads, 0);
    select = true; await click();
    fail = true; await click();
    assert.equal(view.container.querySelector("textarea")?.value, "识别成功");
    assert.match(view.container.textContent ?? "", /账户额度不足/);
    assert.equal(view.container.querySelector("button")?.disabled, false);
  } finally { await view.cleanup(); }
});
