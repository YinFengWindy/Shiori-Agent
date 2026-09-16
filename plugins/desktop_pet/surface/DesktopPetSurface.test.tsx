import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { DesktopPetSurface } from "./DesktopPetSurface";
import { petBubbleGap } from "./bubbleExtension";
import type {
  SurfacePlacement,
  SurfaceHandle,
} from "../../../apps/desktop/renderer/src/surface/pluginSurfaceRegistry";

type SurfaceCall = { name: string; args: unknown[] };

const spritesheetUrl = "mira-asset://pet";

const placement: SurfacePlacement = {
  anchor: { x: 400, y: 300 },
  bodyOffset: { x: 0, y: 0 },
  workArea: { x: 0, y: 0, width: 1920, height: 1080 },
};

/** A surface whose host-side pushes the test drives by hand. */
function fakeSurface() {
  const calls: SurfaceCall[] = [];
  const stateListeners: ((value: unknown) => void)[] = [];
  const messageListeners: ((value: unknown) => void)[] = [];
  const placementListeners: ((value: SurfacePlacement) => void)[] = [];
  const record = (name: string) => (...args: unknown[]) => { calls.push({ name, args }); };

  const surface = {
    beginDrag: record("beginDrag"),
    endDrag: record("endDrag"),
    setExtension: record("setExtension"),
    setClickThrough: record("setClickThrough"),
    onState: (listener: (value: unknown) => void) => {
      stateListeners.push(listener);
      return () => { stateListeners.splice(stateListeners.indexOf(listener), 1); };
    },
    onMessage: (listener: (value: unknown) => void) => {
      messageListeners.push(listener);
      return () => { messageListeners.splice(messageListeners.indexOf(listener), 1); };
    },
    onPlacement: (listener: (value: SurfacePlacement) => void) => {
      placementListeners.push(listener);
      return () => { placementListeners.splice(placementListeners.indexOf(listener), 1); };
    },
    ready: record("ready"),
    showContextMenu: async () => null,
    activateMainWindow: record("activateMainWindow"),
  } as unknown as SurfaceHandle;

  return {
    surface,
    calls,
    callNames: () => calls.map((call) => call.name),
    extensions: () => calls.filter((call) => call.name === "setExtension").map((call) => call.args[0]),
    listenerCounts: () => ({
      state: stateListeners.length,
      message: messageListeners.length,
      placement: placementListeners.length,
    }),
    async pushState(value: unknown) {
      await act(async () => { for (const listener of [...stateListeners]) listener(value); });
    },
    async pushMessage(value: unknown) {
      await act(async () => { for (const listener of [...messageListeners]) listener(value); });
    },
    async pushPlacement(value: SurfacePlacement) {
      await act(async () => { for (const listener of [...placementListeners]) listener(value); });
    },
  };
}

function fakeMiraDesktop() {
  const voiceListeners: ((value: unknown) => void)[] = [];
  const eventListeners: ((value: unknown) => void)[] = [];
  return {
    bridge: {
      onVoiceState: (listener: (value: unknown) => void) => {
        voiceListeners.push(listener);
        return () => { voiceListeners.splice(voiceListeners.indexOf(listener), 1); };
      },
      onEvent: (listener: (value: unknown) => void) => {
        eventListeners.push(listener);
        return () => { eventListeners.splice(eventListeners.indexOf(listener), 1); };
      },
    },
    counts: () => ({ voice: voiceListeners.length, event: eventListeners.length }),
  };
}

async function mountSurface() {
  const host = fakeSurface();
  const desktop = fakeMiraDesktop();
  const rpcCalls: string[] = [];
  const props = {
    surfaceId: "pet",
    surface: host.surface,
    client: { ...createPluginRpcClient("desktop_pet"), call: async <T,>(method: string) => { rpcCalls.push(method); return { ok: true } as T; } },
  };
  const view = await mountTestComponent(<DesktopPetSurface {...props} />, {
    windowGlobals: { miraDesktop: desktop.bridge },
  });
  return { ...view, host, desktop, rpcCalls };
}

const idleLoad = { load: { package: { spritesheetUrl }, state: "idle" } };

describe("desktop pet surface", () => {
  it("dismisses a persistent bubble through the plugin client", async () => {
    const pet = await mountSurface();
    try {
      await pet.host.pushState({ ...idleLoad, reply: { text: "Windows 已锁定", paused: true, persistent: true } });
      const button = pet.container.querySelector<HTMLButtonElement>(".pet-bubble-dismiss");
      assert.ok(button);
      await act(async () => button.click());
      assert.deepEqual(pet.rpcCalls, ["bubble.dismiss"]);
    } finally {
      await pet.cleanup();
    }
  });
  it("announces readiness so the host replays the retained state", async () => {
    const pet = await mountSurface();
    try {
      assert.equal(pet.host.callNames().includes("ready"), true);
      // Nothing is drawn until the retained state actually arrives: on a
      // transparent window an empty rectangle is the failure mode.
      assert.equal(pet.container.querySelector(".pet-drag-region"), null);
    } finally {
      await pet.cleanup();
    }
  });

  it("renders the sprite from the retained state", async () => {
    const pet = await mountSurface();
    try {
      await pet.host.pushState(idleLoad);

      const sprite = pet.container.querySelector(".pet-drag-region");
      assert.ok(sprite, "the sprite should be rendered once the package arrives");
      assert.match(sprite.getAttribute("style") ?? "", /mira-asset:\/\/pet/);
    } finally {
      await pet.cleanup();
    }
  });

  it("ignores a retained payload it cannot parse instead of rendering a broken pet", async () => {
    const pet = await mountSurface();
    try {
      await pet.host.pushState({ load: { package: {}, state: "dancing" } });

      assert.equal(pet.container.querySelector(".pet-drag-region"), null);
    } finally {
      await pet.cleanup();
    }
  });

  it("shows a reply bubble without restarting the sprite animation", async () => {
    const pet = await mountSurface();
    try {
      await pet.host.pushState(idleLoad);
      // A non-transient play changes the base state the same way the host's
      // `postMessage` does.
      await pet.host.pushMessage({ state: "waiting" });

      // The host resends the whole retained payload when only the reply
      // changed. The sprite must not be reset back to the payload's `idle`.
      await pet.host.pushState({
        ...idleLoad,
        reply: { paused: false, text: "继续写吧", persistent: false },
      });

      const bubble = pet.container.querySelector(".pet-bubble");
      assert.ok(bubble, "the reply bubble should be rendered");
      assert.match(bubble.textContent ?? "", /继续写吧/);
      const sprite = pet.container.querySelector(".pet-drag-region");
      // Row 6 is `waiting`; row 0 would mean the reply clobbered it.
      assert.match(sprite?.getAttribute("style") ?? "", /background-position:[^;]*-1248px/);
    } finally {
      await pet.cleanup();
    }
  });

  it("resets the sprite when the package itself changes", async () => {
    const pet = await mountSurface();
    try {
      await pet.host.pushState(idleLoad);
      await pet.host.pushMessage({ state: "waiting" });
      await pet.host.pushState({ load: { package: { spritesheetUrl: "mira-asset://other" }, state: "idle" } });

      const sprite = pet.container.querySelector(".pet-drag-region");
      assert.match(sprite?.getAttribute("style") ?? "", /mira-asset:\/\/other/);
      assert.match(sprite?.getAttribute("style") ?? "", /background-position:[^;]*0px 0px/);
    } finally {
      await pet.cleanup();
    }
  });

  it("asks the host to extend the window around a measured bubble, exactly once", async () => {
    const pet = await mountSurface();
    try {
      // happy-dom does not do layout, so the bubble's measured height has to be
      // supplied; the component's only input is `scrollHeight`.
      Object.defineProperty(pet.window.HTMLElement.prototype, "scrollHeight", {
        configurable: true,
        get() { return 120; },
      });

      await pet.host.pushPlacement(placement);
      await pet.host.pushState({
        ...idleLoad,
        reply: { paused: false, text: "继续写吧", persistent: false },
      });

      assert.deepEqual(pet.host.extensions(), [{ side: "below", size: 120 + petBubbleGap }]);

      // `setExtension` settles the surface, so the host pushes the placement
      // again. Re-requesting the same extension would loop forever.
      await pet.host.pushPlacement(placement);
      assert.deepEqual(pet.host.extensions(), [{ side: "below", size: 120 + petBubbleGap }]);
    } finally {
      await pet.cleanup();
    }
  });

  it("flips the bubble above the sprite near the bottom of the work area", async () => {
    const pet = await mountSurface();
    try {
      Object.defineProperty(pet.window.HTMLElement.prototype, "scrollHeight", {
        configurable: true,
        get() { return 120; },
      });

      await pet.host.pushPlacement({ ...placement, anchor: { x: 400, y: 900 } });
      await pet.host.pushState({
        ...idleLoad,
        reply: { paused: false, text: "继续写吧", persistent: false },
      });

      assert.deepEqual(pet.host.extensions(), [{ side: "above", size: 120 + petBubbleGap }]);
      assert.ok(pet.container.querySelector(".pet-bubble-above"), "the bubble should render above");
    } finally {
      await pet.cleanup();
    }
  });

  it("unsubscribes from every channel when the surface unmounts", async () => {
    const pet = await mountSurface();
    await pet.host.pushState(idleLoad);
    assert.deepEqual(pet.host.listenerCounts(), { state: 1, message: 1, placement: 1 });
    assert.equal(pet.desktop.counts().voice, 1);

    await pet.cleanup();

    assert.deepEqual(pet.host.listenerCounts(), { state: 0, message: 0, placement: 0 });
    assert.equal(pet.desktop.counts().voice, 0);
  });
});
