import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mountTestComponent } from "./testing/domTestHarness";
import { nameViewTransitionElement, runViewTransition, viewTransitionMode, type StartViewTransition, type ViewTransitionHandle } from "./viewTransition";

/** A controllable stand-in for `document.startViewTransition`. */
function fakeStart() {
  const calls: Array<{ handle: ViewTransitionHandle; finish: () => void; skipped: boolean }> = [];
  const start: StartViewTransition = (update) => {
    let finish!: () => void;
    const finished = new Promise<void>((resolve) => { finish = resolve; });
    const updateCallbackDone = Promise.resolve().then(update);
    const entry = {
      skipped: false,
      finish,
      handle: {
        finished: updateCallbackDone.then(() => finished),
        updateCallbackDone,
        skipTransition: () => { entry.skipped = true; finish(); },
      },
    };
    calls.push(entry);
    return entry.handle;
  };
  return { start, calls };
}

describe("viewTransitionMode", () => {
  it("morphs shared elements only with the API and full motion", () => {
    assert.equal(viewTransitionMode({ supported: true, reducedMotion: false }), "shared");
  });

  it("falls back to a plain crossfade under reduced motion", () => {
    assert.equal(viewTransitionMode({ supported: true, reducedMotion: true }), "crossfade");
  });

  it("changes instantly without the API", () => {
    assert.equal(viewTransitionMode({ supported: false, reducedMotion: false }), "none");
    assert.equal(viewTransitionMode({ supported: false, reducedMotion: true }), "none");
  });
});

describe("runViewTransition", () => {
  it("runs the update directly when the API is missing", async () => {
    const order: string[] = [];
    await runViewTransition({ start: null, reducedMotion: false, update: () => order.push("update"), nameOld: () => order.push("old"), nameNew: () => order.push("new") });
    assert.deepEqual(order, ["update"]);
  });

  it("names the old view, updates, then names the new view in shared mode", async () => {
    const view = await mountTestComponent(null);
    try {
      const { start, calls } = fakeStart();
      const order: string[] = [];
      const done = runViewTransition({ start, reducedMotion: false, update: () => order.push("update"), nameOld: () => order.push("old"), nameNew: () => order.push("new") });
      await calls[0]!.handle.updateCallbackDone;
      calls[0]!.finish();
      await done;
      assert.deepEqual(order, ["old", "update", "new"]);
    } finally { await view.cleanup(); }
  });

  it("names nothing under reduced motion but still transitions", async () => {
    const view = await mountTestComponent(null);
    try {
      const { start, calls } = fakeStart();
      const order: string[] = [];
      const done = runViewTransition({ start, reducedMotion: true, update: () => order.push("update"), nameOld: () => order.push("old"), nameNew: () => order.push("new") });
      await calls[0]!.handle.updateCallbackDone;
      calls[0]!.finish();
      await done;
      assert.deepEqual(order, ["update"]);
      assert.equal(calls.length, 1);
    } finally { await view.cleanup(); }
  });

  it("skips a running transition before starting the next one", async () => {
    const view = await mountTestComponent(null);
    try {
      const { start, calls } = fakeStart();
      const first = runViewTransition({ start, reducedMotion: false, update: () => undefined });
      await calls[0]!.handle.updateCallbackDone;
      const second = runViewTransition({ start, reducedMotion: false, update: () => undefined });
      await first;
      assert.equal(calls[0]!.skipped, true);
      await new Promise((resolve) => setTimeout(resolve, 0));
      calls[1]!.finish();
      await second;
      assert.equal(calls.length, 2);
    } finally { await view.cleanup(); }
  });

  it("clears the names it set once the transition finishes", async () => {
    const view = await mountTestComponent(<div data-testid="named" />);
    try {
      const { start, calls } = fakeStart();
      const element = view.container.querySelector("[data-testid=\"named\"]");
      const done = runViewTransition({ start, reducedMotion: false, update: () => undefined, nameNew: () => nameViewTransitionElement(element, "role-name") });
      await calls[0]!.handle.updateCallbackDone;
      assert.equal((element as HTMLElement).style.viewTransitionName, "role-name");
      calls[0]!.finish();
      await done;
      assert.equal((element as HTMLElement).style.viewTransitionName, "");
    } finally { await view.cleanup(); }
  });
});
