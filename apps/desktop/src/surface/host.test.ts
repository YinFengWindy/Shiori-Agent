import assert from "node:assert/strict";
import { test } from "node:test";
import type { SurfaceBounds, SurfaceSpec } from "./contract.js";
import {
  DesktopSurfaceError,
  DesktopSurfaceHost,
  surfaceMessageChannel,
  surfacePositionChannel,
  surfaceStateChannel,
  type DesktopSurfaceHostOptions,
  type SurfaceKey,
  type SurfaceSettleReason,
  type SurfaceWindowHandle,
} from "./host.js";

const body = { width: 192, height: 208 };
const spec: SurfaceSpec = { body };
const key: SurfaceKey = { pluginId: "demo", surfaceId: "main" };
const workArea = { x: 0, y: 0, width: 1920, height: 1040 };

class FakeWindow implements SurfaceWindowHandle {
  static nextId = 1;
  readonly id = FakeWindow.nextId++;
  bounds: SurfaceBounds = { x: 0, y: 0, width: body.width, height: body.height };
  destroyed = false;
  hidden = false;
  shown = 0;
  ignoreMouse: { ignore: boolean; forward?: boolean } | null = null;
  readonly sent: { channel: string; payload: unknown }[] = [];
  private closedListeners: (() => void)[] = [];

  setBounds(bounds: SurfaceBounds) { this.bounds = bounds; }
  getBounds() { return this.bounds; }
  isDestroyed() { return this.destroyed; }
  destroy() { this.destroyed = true; }
  showInactive() { this.shown += 1; this.hidden = false; }
  hide() { this.hidden = true; }
  setIgnoreMouseEvents(ignore: boolean, options?: { forward?: boolean }) {
    this.ignoreMouse = { ignore, forward: options?.forward };
  }
  send(channel: string, payload: unknown) { this.sent.push({ channel, payload }); }
  onClosed(listener: () => void) { this.closedListeners.push(listener); }
  /** Simulates the OS closing the window out from under the host. */
  emitClosed() { this.destroyed = true; for (const listener of this.closedListeners) listener(); }
  positionMessages() { return this.sent.filter((item) => item.channel === surfacePositionChannel); }
}

type Scheduled = { id: number; dueAtMs: number; callback: () => void };

/** A deterministic clock plus timer queue, so glide and tween frames are exact. */
class FakeClock {
  nowMs = 1_000;
  private nextId = 1;
  private queue: Scheduled[] = [];

  setTimer = (callback: () => void, delayMs: number) => {
    const entry = { id: this.nextId++, dueAtMs: this.nowMs + delayMs, callback };
    this.queue.push(entry);
    return entry.id as unknown as ReturnType<typeof setTimeout>;
  };

  clearTimer = (handle: unknown) => {
    this.queue = this.queue.filter((entry) => entry.id !== (handle as number));
  };

  get pending() { return this.queue.length; }

  /** Runs every timer that comes due within `byMs`, in due order. */
  advance(byMs: number) {
    const deadline = this.nowMs + byMs;
    for (;;) {
      const next = this.queue.slice().sort((a, b) => a.dueAtMs - b.dueAtMs)[0];
      if (!next || next.dueAtMs > deadline) break;
      this.queue = this.queue.filter((entry) => entry !== next);
      this.nowMs = next.dueAtMs;
      next.callback();
    }
    this.nowMs = deadline;
  }
}

function setup(options: {
  cursor?: () => { x: number; y: number };
  displayId?: () => string;
  onSettled?: DesktopSurfaceHostOptions["onSettled"];
} = {}) {
  const clock = new FakeClock();
  const windows: FakeWindow[] = [];
  let cursor = { x: 0, y: 0 };
  const host = new DesktopSurfaceHost({
    createWindow: () => { const window = new FakeWindow(); windows.push(window); return window; },
    workAreaFor: () => workArea,
    displayIdFor: options.displayId,
    cursorScreenPoint: options.cursor ?? (() => cursor),
    onSettled: options.onSettled,
    now: () => clock.nowMs,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
  });
  return { host, clock, windows, moveCursor: (next: { x: number; y: number }) => { cursor = next; } };
}

/** Collects settle notifications, which is how main-process owners track a surface. */
function settleRecorder() {
  const settles: { key: SurfaceKey; anchor: { x: number; y: number }; reason: SurfaceSettleReason }[] = [];
  const onSettled: DesktopSurfaceHostOptions["onSettled"] = (settledKey, placement, reason) => {
    settles.push({ key: settledKey, anchor: placement.anchor, reason });
  };
  return { settles, onSettled, reasons: () => settles.map((settle) => settle.reason) };
}

test("creating a surface places its body and reports the clamped anchor once", () => {
  const { host, windows } = setup();
  const applied = host.create(key, spec, { x: -100, y: 500 });
  assert.deepEqual(applied, { x: 0, y: 500 });
  assert.deepEqual(windows[0].bounds, { x: 0, y: 500, width: 192, height: 208 });
  assert.deepEqual(windows[0].positionMessages().length, 1);
  assert.deepEqual(windows[0].positionMessages()[0].payload, {
    anchor: { x: 0, y: 500 },
    bodyOffset: { x: 0, y: 0 },
    workArea,
  });
});

test("creating the same surface twice is refused rather than leaking the first window", () => {
  const { host, windows } = setup();
  host.create(key, spec, { x: 0, y: 0 });
  assert.throws(() => host.create(key, spec, { x: 0, y: 0 }), DesktopSurfaceError);
  assert.equal(windows.length, 1, "the refused call must not have created a second window");
  assert.equal(windows[0].destroyed, false);
});

test("an extension grows the window without moving the body", () => {
  const { host, windows } = setup();
  host.create(key, spec, { x: 300, y: 400 });
  host.setExtension(key, { side: "above", size: 60 });
  assert.deepEqual(windows[0].bounds, { x: 300, y: 340, width: 192, height: 268 });
  const latest = windows[0].positionMessages().at(-1)?.payload as { anchor: unknown; bodyOffset: unknown };
  assert.deepEqual(latest.anchor, { x: 300, y: 400 }, "the body anchor is unchanged");
  assert.deepEqual(latest.bodyOffset, { x: 0, y: 60 });
});

test("a drag follows the native cursor without an IPC message per frame", () => {
  const { host, windows, clock, moveCursor } = setup();
  host.create(key, spec, { x: 300, y: 400 });
  const messagesAfterCreate = windows[0].positionMessages().length;

  moveCursor({ x: 800, y: 700 });
  host.beginDrag(key, { x: 96, y: 104 });
  clock.advance(100);
  assert.deepEqual(windows[0].bounds.x, 800 - 96);
  assert.deepEqual(windows[0].bounds.y, 700 - 104);

  moveCursor({ x: 900, y: 750 });
  clock.advance(100);
  assert.deepEqual(windows[0].bounds.x, 900 - 96);

  assert.equal(
    windows[0].positionMessages().length,
    messagesAfterCreate,
    "drag frames must not push a message per frame — that is the round-trip these primitives exist to avoid",
  );

  host.endDrag(key);
  assert.equal(windows[0].positionMessages().length, messagesAfterCreate + 1, "settling reports once");
  assert.deepEqual(windows[0].positionMessages().at(-1)?.payload, {
    anchor: { x: 804, y: 646 },
    bodyOffset: { x: 0, y: 0 },
    workArea,
  });
});

test("ending a drag stops the cursor follower", () => {
  const { host, windows, clock, moveCursor } = setup();
  host.create(key, spec, { x: 300, y: 400 });
  moveCursor({ x: 800, y: 700 });
  host.beginDrag(key, { x: 0, y: 0 });
  clock.advance(50);
  host.endDrag(key);
  const settled = { ...windows[0].bounds };

  moveCursor({ x: 1200, y: 900 });
  clock.advance(500);
  assert.deepEqual(windows[0].bounds, settled, "the surface must not keep chasing the cursor after release");
  assert.equal(clock.pending, 0, "no follower timer may survive the release");
});

test("a release velocity glides the surface and settles it exactly once", () => {
  const { host, windows, clock } = setup();
  host.create(key, spec, { x: 300, y: 400 });
  const before = windows[0].positionMessages().length;
  host.endDrag(key, { x: 900, y: 0 });
  clock.advance(2_000);
  assert.ok(windows[0].bounds.x > 300, "the glide must have carried the surface forward");
  assert.equal(clock.pending, 0, "the glide must not leave a timer behind");
  assert.equal(windows[0].positionMessages().length, before + 1);
});

test("a glide into an edge slides along it instead of stopping dead", () => {
  const { host, windows, clock } = setup();
  // Flick hard into the right edge with a live downward component: the x axis
  // clamps immediately, the y axis must keep travelling.
  host.create(key, spec, { x: 1920 - body.width, y: 100 });
  host.endDrag(key, { x: 5_000, y: 900 });
  clock.advance(2_000);
  assert.equal(windows[0].bounds.x, 1920 - body.width);
  assert.ok(windows[0].bounds.y > 100, "the unclamped axis must have kept gliding");
});

test("a glide into a corner settles immediately instead of burning the full duration", () => {
  const { host, windows, clock } = setup();
  host.create(key, spec, { x: 1920 - body.width, y: 1040 - body.height });
  host.endDrag(key, { x: 5_000, y: 5_000 });
  // Both axes clamp on the very first frame, so both velocities are spent and
  // the glide has nowhere left to go. Without per-axis zeroing it would keep
  // integrating an undiminished velocity against a pinned position until the
  // 900ms ceiling — still on screen, but holding a timer for no reason.
  clock.advance(50);
  assert.equal(clock.pending, 0, "a glide with nowhere to go must settle on the first frame");
  assert.equal(windows[0].positionMessages().length, 2, "create reports once, the settle reports once");
  assert.deepEqual(windows[0].bounds, {
    x: 1920 - body.width,
    y: 1040 - body.height,
    width: body.width,
    height: body.height,
  });
});

test("an eased move interpolates and lands exactly on the target", () => {
  const { host, windows, clock } = setup();
  host.create(key, spec, { x: 100, y: 100 });
  host.moveTo(key, { x: 700, y: 100 }, 900);
  clock.advance(450);
  const midway = windows[0].bounds.x;
  assert.ok(midway > 100 && midway < 700, `expected an intermediate frame, got ${midway}`);
  clock.advance(900);
  assert.equal(windows[0].bounds.x, 700);
  assert.equal(clock.pending, 0);
});

test("a new interaction cancels the one in flight", () => {
  const { host, windows, clock, moveCursor } = setup();
  host.create(key, spec, { x: 100, y: 100 });
  host.moveTo(key, { x: 900, y: 100 }, 900);
  clock.advance(100);

  moveCursor({ x: 400, y: 400 });
  host.beginDrag(key, { x: 0, y: 0 });
  clock.advance(2_000);
  assert.deepEqual(windows[0].bounds.x, 400, "the drag, not the abandoned tween, owns the position");

  host.endDrag(key);
  assert.equal(clock.pending, 0);
});

test("destroying a surface stops its timers and closes its window", () => {
  const { host, windows, clock } = setup();
  host.create(key, spec, { x: 100, y: 100 });
  host.endDrag(key, { x: 900, y: 900 });
  assert.ok(clock.pending > 0);
  host.destroy(key);
  assert.equal(clock.pending, 0);
  assert.equal(windows[0].destroyed, true);
  assert.equal(host.has(key), false);
});

test("disabling a plugin reclaims every surface it owns, and only those", () => {
  const { host, windows } = setup();
  host.create({ pluginId: "demo", surfaceId: "a" }, spec, { x: 0, y: 0 });
  host.create({ pluginId: "demo", surfaceId: "b" }, spec, { x: 0, y: 0 });
  host.create({ pluginId: "other", surfaceId: "a" }, spec, { x: 0, y: 0 });

  host.destroyAllForPlugin("demo");

  assert.equal(host.has({ pluginId: "demo", surfaceId: "a" }), false);
  assert.equal(host.has({ pluginId: "demo", surfaceId: "b" }), false);
  assert.equal(host.has({ pluginId: "other", surfaceId: "a" }), true);
  assert.deepEqual(windows.map((item) => item.destroyed), [true, true, false]);
});

test("a window closed by the OS is forgotten and its timers dropped", () => {
  const { host, windows, clock } = setup();
  host.create(key, spec, { x: 100, y: 100 });
  host.endDrag(key, { x: 900, y: 900 });
  assert.ok(clock.pending > 0);

  windows[0].emitClosed();

  assert.equal(host.has(key), false);
  assert.equal(clock.pending, 0, "a glide must not keep ticking against a window the OS already closed");
  assert.throws(() => host.setPosition(key, { x: 0, y: 0 }), DesktopSurfaceError);
});

test("an IPC sender is attributed only to the live surface that owns its window", () => {
  const { host, windows } = setup();
  host.create(key, spec, { x: 0, y: 0 });
  assert.deepEqual(host.keyForWindowId(windows[0].id), key);
  assert.equal(host.keyForWindowId(windows[0].id + 999), null);
  assert.equal(host.keyForWindowId(null), null);
  host.destroy(key);
  assert.equal(host.keyForWindowId(windows[0].id), null, "a destroyed surface must not claim its old window id");
});

test("click-through is applied at creation and toggled afterwards", () => {
  const { host, windows } = setup();
  host.create(key, { body, clickThrough: true }, { x: 0, y: 0 });
  assert.deepEqual(windows[0].ignoreMouse, { ignore: true, forward: true });
  host.setClickThrough(key, false);
  assert.deepEqual(windows[0].ignoreMouse, { ignore: false, forward: true });
});

test("hiding a surface stops interactions rather than leaving them running offscreen", () => {
  const { host, windows, clock } = setup();
  host.create(key, spec, { x: 100, y: 100 });
  host.endDrag(key, { x: 900, y: 900 });
  host.hide(key);
  assert.equal(windows[0].hidden, true);
  assert.equal(clock.pending, 0);
});

test("messages are relayed only to the plugin's own surface", () => {
  const { host, windows } = setup();
  host.create(key, spec, { x: 0, y: 0 });
  host.create({ pluginId: "other", surfaceId: "main" }, spec, { x: 0, y: 0 });
  host.postMessage(key, { hello: "world" });
  assert.deepEqual(
    windows[0].sent.filter((item) => item.channel === surfaceMessageChannel).map((item) => item.payload),
    [{ hello: "world" }],
  );
  assert.equal(windows[1].sent.some((item) => item.channel === surfaceMessageChannel), false);
});

test("posting to a surface that is already gone is a no-op, not a throw", () => {
  const { host } = setup();
  host.postMessage(key, { hello: "world" });
});

test("retained state is replayed when the renderer reports ready", () => {
  const { host, windows } = setup();
  host.create(key, spec, { x: 100, y: 100 });
  // State set before the renderer finished mounting. Without replay the window
  // comes up blank, which on a transparent surface is indistinguishable from
  // "the plugin is broken".
  host.setState(key, { sprite: "idle" });

  host.markReady(key);

  assert.deepEqual(
    windows[0].sent.filter((item) => item.channel === surfaceStateChannel).map((item) => item.payload),
    [{ sprite: "idle" }, { sprite: "idle" }],
  );
  assert.equal(
    windows[0].positionMessages().length,
    2,
    "ready must also replay the placement, so the renderer can lay out without asking",
  );
});

test("only the latest retained state is replayed, and transient messages never are", () => {
  const { host, windows } = setup();
  host.create(key, spec, { x: 0, y: 0 });
  host.setState(key, { sprite: "idle" });
  host.setState(key, { sprite: "walk" });
  host.postMessage(key, { play: "wave" });

  const before = windows[0].sent.length;
  host.markReady(key);

  const replayed = windows[0].sent.slice(before);
  assert.deepEqual(
    replayed.filter((item) => item.channel === surfaceStateChannel).map((item) => item.payload),
    [{ sprite: "walk" }],
  );
  assert.equal(
    replayed.some((item) => item.channel === surfaceMessageChannel),
    false,
    "a one-shot 'play this animation' must not fire again on every reload",
  );
});

test("ready on a surface that is already gone is refused rather than crashed on", () => {
  const { host } = setup();
  assert.throws(() => host.markReady(key), DesktopSurfaceError);
});

test("a surface is revealed only once its renderer reports ready", () => {
  const { host, windows } = setup();
  host.create(key, spec, { x: 0, y: 0 });
  // Showing at create would put an empty transparent always-on-top rectangle
  // over the desktop until the renderer painted.
  assert.equal(windows[0].shown, 0);

  host.show(key);
  assert.equal(windows[0].shown, 0, "an early show request cannot bypass readiness");

  host.markReady(key);

  assert.equal(windows[0].shown, 1);
});

test("hide before ready cancels an early show request until explicitly shown again", () => {
  const { host, windows } = setup();
  host.create(key, spec, { x: 0, y: 0 });
  host.show(key);
  host.hide(key);
  host.markReady(key);
  assert.equal(windows[0].shown, 0);
  assert.equal(windows[0].hidden, true);
  host.show(key);
  assert.equal(windows[0].shown, 1);
});

test("a renderer reload does not resurrect a surface the plugin hid", () => {
  const { host, windows } = setup();
  host.create(key, spec, { x: 0, y: 0 });
  host.markReady(key);
  host.hide(key);
  assert.equal(windows[0].hidden, true);

  // A reloaded renderer announces itself again; the surface must stay hidden.
  host.markReady(key);

  assert.equal(windows[0].hidden, true);
  assert.equal(windows[0].shown, 1);

  host.show(key);
  host.markReady(key);
  assert.equal(windows[0].shown, 3);
});

test("the settle observer is told where a surface came to rest, and why", () => {
  const recorder = settleRecorder();
  const { host } = setup({ onSettled: recorder.onSettled });

  host.create(key, spec, { x: 300, y: 400 });
  host.setPosition(key, { x: 500, y: 600 });
  host.setExtension(key, { side: "above", size: 60 });
  host.markReady(key);

  assert.deepEqual(recorder.reasons(), ["create", "position", "extension", "ready"]);
  assert.deepEqual(recorder.settles.at(-1)?.key, key);
  assert.deepEqual(recorder.settles.at(-1)?.anchor, { x: 500, y: 600 });
});

test("the settle observer is not called per drag, glide or tween frame", () => {
  const recorder = settleRecorder();
  const { host, clock, windows, moveCursor } = setup({ onSettled: recorder.onSettled });
  host.create(key, spec, { x: 300, y: 400 });

  moveCursor({ x: 800, y: 700 });
  host.beginDrag(key, { x: 96, y: 104 });
  clock.advance(200);
  assert.deepEqual(recorder.reasons(), ["create"], "cursor following must not notify per frame");
  assert.ok(windows[0].bounds.x > 300, "the drag should genuinely have moved the window");

  host.endDrag(key, { x: -900, y: 0 });
  assert.deepEqual(recorder.reasons(), ["create"], "handing over a velocity is not settling");
  clock.advance(40);
  assert.deepEqual(recorder.reasons(), ["create"], "glide frames must not notify per frame");

  clock.advance(2_000);
  assert.deepEqual(recorder.reasons(), ["create", "momentum"], "the glide settles exactly once");

  host.moveTo(key, { x: 100, y: 100 }, 200);
  clock.advance(100);
  assert.deepEqual(recorder.reasons(), ["create", "momentum"], "tween frames must not notify per frame");
  clock.advance(400);
  assert.deepEqual(recorder.reasons(), ["create", "momentum", "move"]);
  assert.deepEqual(recorder.settles.at(-1)?.anchor, { x: 100, y: 100 });
});

test("a drag released without a velocity settles immediately", () => {
  const recorder = settleRecorder();
  const { host, clock, moveCursor } = setup({ onSettled: recorder.onSettled });
  host.create(key, spec, { x: 300, y: 400 });

  moveCursor({ x: 500, y: 500 });
  host.beginDrag(key, { x: 0, y: 0 });
  clock.advance(50);
  host.endDrag(key);

  assert.deepEqual(recorder.reasons(), ["create", "drag"]);
  assert.deepEqual(recorder.settles.at(-1)?.anchor, { x: 500, y: 500 });
});

test("a settle observer that throws does not break the surface it observes", () => {
  let calls = 0;
  const { host, clock, windows } = setup({
    onSettled: () => { calls += 1; throw new Error("observer exploded"); },
  });

  host.create(key, spec, { x: 300, y: 400 });
  // A throwing observer is called from glide and tween timers; letting it
  // escape would strand the surface mid-motion with a dead timer.
  host.endDrag(key, { x: -900, y: 0 });
  clock.advance(2_000);
  host.setPosition(key, { x: 10, y: 20 });

  assert.ok(calls >= 3);
  assert.deepEqual(windows[0].bounds, { x: 10, y: 20, width: 192, height: 208 });
  assert.equal(host.has(key), true);
});

test("display identity is separate from the work-area rectangle", () => {
  const { host } = setup({ displayId: () => "display-7" });
  host.create(key, spec, { x: 0, y: 0 });

  assert.equal(host.displayId(key), "display-7");
  assert.deepEqual(host.workArea(key), workArea);
});

test("display identity falls back to empty rather than throwing when the host cannot report it", () => {
  const { host } = setup();
  host.create(key, spec, { x: 0, y: 0 });

  assert.equal(host.displayId(key), "");
});

test("a context menu resolves the chosen id and targets the surface's own window", async () => {
  const seen: { id: number; items: { id: string; label: string }[] }[] = [];
  const windows: FakeWindow[] = [];
  const host = new DesktopSurfaceHost({
    createWindow: () => { const window = new FakeWindow(); windows.push(window); return window; },
    workAreaFor: () => workArea,
    cursorScreenPoint: () => ({ x: 0, y: 0 }),
    showContextMenu: async (window, items) => {
      seen.push({ id: window.id, items });
      return items[1]?.id ?? null;
    },
  });
  host.create(key, spec, { x: 0, y: 0 });

  const chosen = await host.showContextMenu(key, [
    { id: "open", label: "显示主窗口" },
    { id: "hide", label: "隐藏" },
  ]);

  assert.equal(chosen, "hide");
  assert.equal(seen.length, 1);
  assert.equal(seen[0].id, windows[0].id);
});

test("an empty menu resolves null without bothering the platform", async () => {
  let called = 0;
  const host = new DesktopSurfaceHost({
    createWindow: () => new FakeWindow(),
    workAreaFor: () => workArea,
    cursorScreenPoint: () => ({ x: 0, y: 0 }),
    showContextMenu: async () => { called += 1; return null; },
  });
  host.create(key, spec, { x: 0, y: 0 });
  assert.equal(await host.showContextMenu(key, []), null);
  assert.equal(called, 0, "an empty menu must not pop an empty native menu");
});

test("a host without menu support resolves null instead of throwing", async () => {
  const { host } = setup();
  host.create(key, spec, { x: 0, y: 0 });
  assert.equal(await host.showContextMenu(key, [{ id: "a", label: "A" }]), null);
});

test("activating the main window is forwarded, and tolerated when unsupported", () => {
  let activated = 0;
  const host = new DesktopSurfaceHost({
    createWindow: () => new FakeWindow(),
    workAreaFor: () => workArea,
    cursorScreenPoint: () => ({ x: 0, y: 0 }),
    activateMainWindow: () => { activated += 1; },
  });
  host.activateMainWindow();
  assert.equal(activated, 1);

  const { host: bare } = setup();
  bare.activateMainWindow();
});

test("hasAny reports whether the app still owns a desktop window", () => {
  const { host } = setup();
  assert.equal(host.hasAny(), false, "nothing created yet");

  host.create({ pluginId: "demo", surfaceId: "one" }, spec, { x: 0, y: 0 });
  host.create({ pluginId: "other", surfaceId: "two" }, spec, { x: 0, y: 0 });
  assert.equal(host.hasAny(), true);

  // The main window's close policy reads this: one plugin going away must not
  // make the shell closable while another still has a window on screen.
  host.destroy({ pluginId: "demo", surfaceId: "one" });
  assert.equal(host.hasAny(), true);

  host.destroy({ pluginId: "other", surfaceId: "two" });
  assert.equal(host.hasAny(), false);
});

test("a window destroyed behind the host's back does not count as alive", () => {
  const { host, windows } = setup();
  host.create({ pluginId: "demo", surfaceId: "one" }, spec, { x: 0, y: 0 });

  // Set directly, without the `onClosed` notification the host normally learns
  // from, so this checks the answer itself rather than the bookkeeping.
  windows[0].destroyed = true;

  assert.equal(host.hasAny(), false);
});

test("destroyAll reclaims every plugin's surface, whoever owns it", () => {
  const { host, windows } = setup();
  host.create({ pluginId: "demo", surfaceId: "one" }, spec, { x: 0, y: 0 });
  host.create({ pluginId: "other", surfaceId: "two" }, spec, { x: 0, y: 0 });

  // What the host does when the renderer driving all of them has died: every
  // surface is frameless and always-on-top, so leaving one is a window the
  // user cannot dismiss.
  host.destroyAll();

  assert.equal(host.hasAny(), false);
  assert.deepEqual(windows.map((window) => window.destroyed), [true, true]);
});
