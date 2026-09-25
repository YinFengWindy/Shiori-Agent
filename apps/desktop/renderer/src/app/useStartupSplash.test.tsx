/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { startupSplashDelayMs, startupSplashExitMs } from "./startupSplashPhase";
import { useStartupSplash } from "./useStartupSplash";

function Probe({ health, enabled }: { health: string; enabled: boolean }) {
  const { phase, leaving } = useStartupSplash(health, enabled);
  return <output data-phase={phase ?? "none"} data-leaving={String(leaving)} />;
}

const wait = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });

function read(container: HTMLElement) {
  const output = container.querySelector("output")!;
  return { phase: output.dataset.phase, leaving: output.dataset.leaving };
}

describe("useStartupSplash", () => {
  it("waits out the delay, then greets, and fades out once the backend answers", async () => {
    const view = await mountTestComponent(<Probe health="connecting" enabled />);
    try {
      assert.equal(read(view.container).phase, "none");
      await wait(startupSplashDelayMs + 80);
      assert.equal(read(view.container).phase, "booting");
      await view.render(<Probe health="online" enabled />);
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

  it("never appears for a startup quicker than the delay", async () => {
    const view = await mountTestComponent(<Probe health="connecting" enabled />);
    try {
      await wait(startupSplashDelayMs / 2);
      await view.render(<Probe health="online" enabled />);
      await wait(startupSplashDelayMs);
      assert.equal(read(view.container).phase, "none");
    } finally {
      await view.cleanup();
    }
  });

  it("shows a failed startup at once and keeps it up through a restart", async () => {
    const view = await mountTestComponent(<Probe health="offline" enabled />);
    try {
      assert.equal(read(view.container).phase, "failed");
      await view.render(<Probe health="connecting" enabled />);
      assert.deepEqual(read(view.container), { phase: "booting", leaving: "false" });
    } finally {
      await view.cleanup();
    }
  });

  it("shows no splash at all with the 看板娘 off", async () => {
    const view = await mountTestComponent(<Probe health="offline" enabled={false} />);
    try {
      assert.equal(read(view.container).phase, "none");
      await view.render(<Probe health="connecting" enabled={false} />);
      await wait(startupSplashDelayMs + 80);
      assert.equal(read(view.container).phase, "none");
    } finally {
      await view.cleanup();
    }
  });
});
