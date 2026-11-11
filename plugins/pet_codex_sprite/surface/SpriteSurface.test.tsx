import React, { act } from "react";
import assert from "node:assert/strict";
import test from "node:test";
import { createFakePluginClient, createFakeSurfaceHandle, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { emptyPetReply } from "@shiori-plugin/desktop_pet/provider";
import { SpriteSurface } from "./SpriteSurface";

test("surface bootstrap is not model readiness, and image failure reports the current lease", async () => {
  let retained: (value: unknown) => void = () => {};
  const messages: unknown[] = [];
  const surface = createFakeSurfaceHandle({ onState: (handler) => { retained = handler; return () => {}; }, postToBackground: (value) => messages.push(value) });
  const view = await mountTestComponent(<SpriteSurface surfaceId="pet-lease" surface={surface} client={createFakePluginClient()} />);
  try {
    assert.deepEqual(messages, []);
    await act(async () => retained({ request_id: "request", lease_id: "lease", role_id: "role", model_id: "model", spritesheetUrl: "shiori-asset://sprite", body: { width: 192, height: 208 }, state: { reply: emptyPetReply, voice: { status: "idle" } } }));
    assert.deepEqual(messages, []);
    const image = view.container.querySelector("img"); assert.ok(image);
    await act(async () => image.dispatchEvent(new Event("error")));
    assert.deepEqual(messages, [{ kind: "model.failed", lease_id: "lease" }]);
  } finally { await view.cleanup(); }
});
