import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { createFakeSurfaceHandle, mountTestComponent } from "@shiori/sdk/testing";
import { useCodexPetInteraction } from "./useCodexPetInteraction";

type BridgeCall = { name: string; args: unknown[] };

/** Records every surface and voice call so tests assert on the exact commands. */
function fakeBridges(calls: BridgeCall[]) {
  const record = (name: string) => (...args: unknown[]) => { calls.push({ name, args }); };
  const surface = createFakeSurfaceHandle({
    beginDrag: record("beginDrag"),
    endDrag: record("endDrag"),
    setExtension: record("setExtension"),
    setClickThrough: record("setClickThrough"),
    onPlacement: () => () => {},
    onMessage: () => () => {},
    onState: () => () => {},
    ready: record("ready"),
    showContextMenu: async () => null,
    activateMainWindow: record("activateMainWindow"),
    voice: {
      gesture: (gesture) => record({ press: "startVoicePress", move: "voicePointerMoved", release: "voiceRelease", cancel: "voiceCancel" }[gesture])(),
      onState: () => () => {},
    },
  });
  return { surface };
}

async function mountPet() {
  const calls: BridgeCall[] = [];
  const { surface } = fakeBridges(calls);
  let hook!: ReturnType<typeof useCodexPetInteraction>;

  function Harness() {
    hook = useCodexPetInteraction(surface);
    return <div data-pet="true" {...hook.pointerHandlers} />;
  }

  const view = await mountTestComponent(<Harness />);
  const element = view.container.querySelector("[data-pet]");
  assert.ok(element, "pet element should be rendered");
  // happy-dom 不实现指针捕获，这里补一个最小实现，让 hook 的捕获/释放分支能真实跑到
  const captured = new Set<number>();
  Object.assign(element, {
    setPointerCapture: (pointerId: number) => { captured.add(pointerId); },
    hasPointerCapture: (pointerId: number) => captured.has(pointerId),
    releasePointerCapture: (pointerId: number) => { captured.delete(pointerId); },
  });

  async function pointer(type: string, init: Record<string, unknown> = {}) {
    await act(async () => {
      element!.dispatchEvent(
        new PointerEvent(type, { bubbles: true, pointerId: 1, button: 0, ...init }),
      );
    });
  }

  async function doubleClick() {
    await act(async () => {
      element!.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    });
  }

  function callNames() {
    return calls.map((call) => call.name);
  }

  return {
    ...view,
    calls,
    callNames,
    capturedPointers: captured,
    pointer,
    doubleClick,
    get state() { return hook.interactionState; },
    get isDragging() { return hook.isDragging; },
  };
}

describe("codex pet interaction", () => {
  it("captures the pointer and starts a surface drag on primary press", async () => {
    const pet = await mountPet();
    try {
      await pet.pointer("pointerdown", { screenX: 100, screenY: 200 });

      assert.equal(pet.isDragging, true);
      assert.deepEqual(pet.callNames(), ["startVoicePress", "beginDrag"]);
      assert.equal(pet.capturedPointers.has(1), true);
    } finally {
      await pet.cleanup();
    }
  });

  it("hands the host a grab offset rather than a screen position", async () => {
    const pet = await mountPet();
    try {
      await pet.pointer("pointerdown", { screenX: 900, screenY: 700, clientX: 17, clientY: 23 });

      const beginDrag = pet.calls.find((call) => call.name === "beginDrag");
      // happy-dom reports a zero-origin bounding rect, so the offset equals the
      // client point. The point of the assertion is the shape: an offset inside
      // the body, never the screen coordinate the old bridge also passed.
      assert.deepEqual(beginDrag?.args, [{ x: 17, y: 23 }]);
    } finally {
      await pet.cleanup();
    }
  });

  it("ignores non-primary buttons", async () => {
    const pet = await mountPet();
    try {
      await pet.pointer("pointerdown", { button: 2, screenX: 100, screenY: 200 });

      assert.equal(pet.isDragging, false);
      assert.deepEqual(pet.callNames(), []);
    } finally {
      await pet.cleanup();
    }
  });

  it("faces the drag direction without reporting a position per pointer move", async () => {
    const pet = await mountPet();
    try {
      await pet.pointer("pointerdown", { screenX: 100, screenY: 200 });
      await pet.pointer("pointermove", { screenX: 101, screenY: 200 });

      assert.equal(pet.state, null, "a sub-threshold move must not change the sprite");
      assert.deepEqual(pet.callNames(), ["startVoicePress", "beginDrag"]);

      await pet.pointer("pointermove", { screenX: 140, screenY: 200 });
      assert.equal(pet.state, "running-right");

      await pet.pointer("pointermove", { screenX: 60, screenY: 200 });
      assert.equal(pet.state, "running-left");
      // The host follows the native cursor itself. A per-move position call
      // from here is precisely what the DesktopSurface primitives replaced, so
      // the only calls left are the voice-gesture cancels.
      assert.deepEqual(pet.callNames().slice(2), ["voicePointerMoved", "voicePointerMoved"]);
    } finally {
      await pet.cleanup();
    }
  });

  it("releases the drag with a throw velocity and drops the pointer capture", async () => {
    const pet = await mountPet();
    try {
      await pet.pointer("pointerdown", { screenX: 100, screenY: 200 });
      await pet.pointer("pointermove", { screenX: 160, screenY: 200 });
      await pet.pointer("pointerup", { screenX: 160, screenY: 200 });

      assert.equal(pet.isDragging, false);
      assert.equal(pet.state, "jumping");
      assert.deepEqual(pet.callNames().slice(-2), ["endDrag", "voiceRelease"]);
      assert.equal(pet.capturedPointers.has(1), false);
    } finally {
      await pet.cleanup();
    }
  });

  it("ends the drag without a velocity when the pointer is cancelled", async () => {
    const pet = await mountPet();
    try {
      await pet.pointer("pointerdown", { screenX: 100, screenY: 200 });
      await pet.pointer("pointercancel", { screenX: 100, screenY: 200 });

      assert.equal(pet.isDragging, false);
      assert.equal(pet.state, null);
      const endDrag = pet.calls.find((call) => call.name === "endDrag");
      assert.deepEqual(endDrag?.args, []);
      assert.deepEqual(pet.callNames().slice(-1), ["voiceCancel"]);
    } finally {
      await pet.cleanup();
    }
  });

  it("activates the main window when a double click follows a click that never moved", async () => {
    const pet = await mountPet();
    try {
      await pet.pointer("pointerdown", { screenX: 100, screenY: 200 });
      await pet.pointer("pointerup", { screenX: 100, screenY: 200 });
      await pet.doubleClick();

      assert.equal(pet.callNames().includes("activateMainWindow"), true);
    } finally {
      await pet.cleanup();
    }
  });

  it("does not activate the main window when the gesture before the double click was a drag", async () => {
    const pet = await mountPet();
    try {
      await pet.pointer("pointerdown", { screenX: 100, screenY: 200 });
      await pet.pointer("pointermove", { screenX: 400, screenY: 200 });
      await pet.pointer("pointerup", { screenX: 400, screenY: 200 });
      await pet.doubleClick();

      assert.equal(pet.callNames().includes("activateMainWindow"), false);
    } finally {
      await pet.cleanup();
    }
  });

  it("shows the hover state only while no drag is in flight", async () => {
    const pet = await mountPet();
    try {
      // React 把 enter/leave 从 over/out 派生出来，所以这里派发的是原生事件
      await pet.pointer("pointerover", { relatedTarget: null });
      assert.equal(pet.state, "jumping");

      await pet.pointer("pointerout", { relatedTarget: null });
      assert.equal(pet.state, null);

      await pet.pointer("pointerdown", { screenX: 100, screenY: 200 });
      await pet.pointer("pointerover", { relatedTarget: null });
      assert.equal(pet.state, null, "hover must not override an in-flight drag");
    } finally {
      await pet.cleanup();
    }
  });
});
