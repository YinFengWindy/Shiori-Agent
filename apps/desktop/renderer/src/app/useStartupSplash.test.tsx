/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it, type TestContext } from "node:test";
import { act } from "react";
import { mockableWindowTimers, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { startupSplashExitMs, startupSplashMinMs } from "./startupSplashPhase";
import { useStartupSplash } from "./useStartupSplash";

function Probe({ health, enabled }: { health: string; enabled: boolean }) {
  const { phase, leaving } = useStartupSplash(health, enabled);
  return <output data-phase={phase ?? "none"} data-leaving={String(leaving)} />;
}

/**
 * Fakes both clocks the hook reads — its window timers and `Date.now` — and
 * returns a `wait` that advances them together inside `act`.
 */
function fakeClock(t: TestContext) {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  return (ms: number) => act(async () => t.mock.timers.tick(ms));
}

function read(container: HTMLElement) {
  const output = container.querySelector("output")!;
  return { phase: output.dataset.phase, leaving: output.dataset.leaving };
}

describe("useStartupSplash", () => {
  it("greets at once and holds a quick startup until 3 seconds after launch, then fades out", async (t) => {
    const wait = fakeClock(t);
    const view = await mountTestComponent(<Probe health="connecting" enabled />, { windowGlobals: mockableWindowTimers });
    try {
      assert.equal(read(view.container).phase, "booting");
      await wait(1000);
      await view.render(<Probe health="online" enabled />);
      assert.deepEqual(read(view.container), { phase: "booting", leaving: "false" });
      await wait(startupSplashMinMs - 1000 - 80);
      assert.deepEqual(read(view.container), { phase: "booting", leaving: "false" });
      await wait(80);
      assert.deepEqual(read(view.container), { phase: "booting", leaving: "true" });
      await wait(startupSplashExitMs + 80);
      assert.equal(read(view.container).phase, "none");
      // A later drop is the offline banner's job, not the splash's.
      await view.render(<Probe health="offline" enabled />);
      assert.equal(read(view.container).phase, "none");
    } finally {
      await view.cleanup();
    }
  });

  it("fades out at once for a startup slower than 3 seconds", async (t) => {
    const wait = fakeClock(t);
    const view = await mountTestComponent(<Probe health="connecting" enabled />, { windowGlobals: mockableWindowTimers });
    try {
      await wait(startupSplashMinMs + 500);
      await view.render(<Probe health="online" enabled />);
      assert.deepEqual(read(view.container), { phase: "booting", leaving: "true" });
    } finally {
      await view.cleanup();
    }
  });

  it("shows a failed startup at once, keeps it up through a restart, and fades out as soon as that answers", async (t) => {
    fakeClock(t);
    const view = await mountTestComponent(<Probe health="offline" enabled />, { windowGlobals: mockableWindowTimers });
    try {
      assert.equal(read(view.container).phase, "failed");
      await view.render(<Probe health="connecting" enabled />);
      assert.deepEqual(read(view.container), { phase: "booting", leaving: "false" });
      await view.render(<Probe health="online" enabled />);
      assert.deepEqual(read(view.container), { phase: "booting", leaving: "true" });
    } finally {
      await view.cleanup();
    }
  });

  it("shows no splash at all with the 看板娘 off", async (t) => {
    const wait = fakeClock(t);
    const view = await mountTestComponent(<Probe health="offline" enabled={false} />, { windowGlobals: mockableWindowTimers });
    try {
      assert.equal(read(view.container).phase, "none");
      await view.render(<Probe health="connecting" enabled={false} />);
      await wait(startupSplashMinMs + 80);
      assert.equal(read(view.container).phase, "none");
    } finally {
      await view.cleanup();
    }
  });
});
