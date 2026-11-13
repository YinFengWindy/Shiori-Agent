import React from "react";
import assert from "node:assert/strict";
import test from "node:test";
import type { SurfaceExtension, SurfacePlacement } from "@yinfengwindy/shiori-sdk";
import { createFakeSurfaceHandle, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { PetShell } from "./PetShell";
import type { PetPresentationState } from "./protocol";

test("preparing the next spoken segment preserves reply content and its dismiss control", async () => {
  const surface = createFakeSurfaceHandle();
  const reply = { text: "这是一段还在连续播报的长回复。后面的内容应该一直可读。", persistent: true, paused: false };
  const render = (status: PetPresentationState["voice"]["status"]) => <PetShell surface={surface} body={{ width: 192, height: 208 }} state={{ reply, voice: { status } }}>{() => null}</PetShell>;
  const view = await mountTestComponent(render("speaking"));
  try {
    await view.render(render("speaking_prepare"));
    assert.equal(view.container.querySelector('[role="status"] span')?.textContent, reply.text);
    assert.ok(view.container.querySelector('button[aria-label="关闭消息"]'));
    await view.render(render("speaking"));
    assert.equal(view.container.querySelector('[role="status"] span')?.textContent, reply.text);
  } finally { await view.cleanup(); }
});

test("a shell mounted after initial surface readiness replays placement and expands its first bubble", async () => {
  const view = await mountTestComponent(null);
  const listeners = new Set<(value: SurfacePlacement) => void>();
  const extensions: SurfaceExtension[] = [];
  const placement = { anchor: { x: 50, y: 50 }, bodyOffset: { x: 0, y: 0 }, workArea: { x: 0, y: 0, width: 1000, height: 1000 } };
  let readyCount = 0;
  const surface = createFakeSurfaceHandle({
    onPlacement: (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    ready: () => { readyCount += 1; for (const listener of listeners) listener(placement); },
    setExtension: (extension) => { extensions.push(extension); for (const listener of listeners) listener(placement); },
  });
  const render = (text: string) => <PetShell surface={surface} body={{ width: 192, height: 208 }} state={{ reply: { text, persistent: false, paused: false }, voice: { status: "idle" } }}>{() => null}</PetShell>;
  try {
    Object.defineProperty(view.window.HTMLElement.prototype, "scrollHeight", { configurable: true, get: () => 80 });
    surface.ready(); // The outer surface mounts first, before the retained model creates its shell.
    await view.render(render("首次回复"));
    assert.deepEqual(extensions, [{ side: "below", size: 86 }]);
    assert.equal(readyCount, 2);
    await view.render(render("后续回复"));
    assert.equal(readyCount, 2, "reply renders must not restart the retained-state replay");
    assert.equal(extensions.length, 1, "placement feedback must not create a resize loop");
  } finally { await view.cleanup(); }
  assert.equal(listeners.size, 0);
});
