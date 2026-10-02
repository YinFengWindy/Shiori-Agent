import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@shiori/sdk/testing";
import { ChatContextRing } from "./ChatContextRing";
import type { ChatContextStatus } from "./chatContextState";

test("the ring remains keyboard-focusable when unavailable and reports readable reasons", async () => {
  let calls = 0;
  const view = await mountTestComponent(<ChatContextRing status={null} busy={false} notice="" unavailable="桌面服务未连接" onCompact={async () => { calls++; }} />);
  try {
    const button = view.container.querySelector("button")!;
    assert.match(button.getAttribute("aria-label") ?? "", /上下文用量未知.*桌面服务未连接/);
    assert.equal(button.disabled, false);
    assert.equal(button.getAttribute("aria-disabled"), "true");
    await act(async () => { button.click(); button.focus(); });
    assert.equal(calls, 0);
    assert.equal(document.activeElement, button);
    assert.match(document.querySelector('[role="tooltip"]')?.textContent ?? "", /用量未知/);
  } finally { await view.cleanup(); }
});

test("the button triggers one transaction and the busy state has no fake progress value", async () => {
  const status: ChatContextStatus = { session_key: "role:mira", context_key: "user", model: "m", model_identity: "m", tokens: 32000, source: "actual", model_context_window: 128000, input_limit_tokens: 100000, can_compact: true, busy: false, reason: "", result: null };
  let calls = 0;
  const onCompact = async () => { calls++; };
  const view = await mountTestComponent(<ChatContextRing status={status} busy={false} notice="" unavailable="" onCompact={onCompact} />);
  try {
    await act(async () => view.container.querySelector("button")!.click());
    assert.equal(calls, 1);
    await view.render(<ChatContextRing status={status} busy notice="" unavailable="正在整理记忆并压缩上下文" onCompact={onCompact} />);
    await act(async () => view.container.querySelector("button")!.click());
    assert.equal(calls, 1);
    assert.equal(view.container.querySelector("button")?.getAttribute("aria-busy"), "true");
    assert.match(view.container.querySelector("button")?.getAttribute("aria-label") ?? "", /25%.*正在整理记忆/);
    assert.equal(view.container.querySelector('[role="progressbar"]'), null);
  } finally { await view.cleanup(); }
});
