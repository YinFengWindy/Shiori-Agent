/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { startupFailedLine, startupGreetingLines, startupSlowLine } from "../shared/mascot/mascotLines";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { StartupSplash } from "./StartupSplash";

const greetings = Object.values(startupGreetingLines).flat().map((line) => line.text);
const lineOf = (container: HTMLElement) => container.querySelector('[data-testid="mascot-line"] .mascot-bubble-text')?.textContent ?? "";

describe("StartupSplash", () => {
  it("greets with a time-of-day line over the loading sparkles while booting, then remarks on a slow start", async () => {
    const view = await mountTestComponent(<StartupSplash phase="booting" leaving={false} windowMaximized={false} onRestart={async () => undefined} />);
    try {
      assert.ok(greetings.includes(lineOf(view.container)), lineOf(view.container));
      assert.ok(view.container.querySelector('[role="status"][aria-label="正在启动"]'));
      assert.equal(view.container.querySelector("main button"), null);
      await view.render(<StartupSplash phase="slow" leaving={false} windowMaximized={false} onRestart={async () => undefined} />);
      assert.equal(lineOf(view.container), startupSlowLine.text);
      assert.equal(view.container.querySelector('[data-testid="mascot-half"]')?.getAttribute("data-expression"), startupSlowLine.expression);
    } finally {
      await view.cleanup();
    }
  });

  it("offers 重启连接 on a failed startup and holds it while the restart runs", async () => {
    let restarts = 0;
    let finish!: () => void;
    const onRestart = () => {
      restarts += 1;
      return new Promise<void>((resolve) => { finish = resolve; });
    };
    const view = await mountTestComponent(<StartupSplash phase="failed" leaving={false} windowMaximized={false} onRestart={onRestart} />);
    try {
      assert.equal(lineOf(view.container), startupFailedLine.text);
      const button = view.container.querySelector<HTMLButtonElement>("main button")!;
      assert.equal(button.textContent?.trim(), "重启连接");
      await act(async () => button.click());
      assert.equal(restarts, 1);
      assert.equal(button.disabled, true);
      await act(async () => finish());
      assert.equal(button.disabled, false);
    } finally {
      await view.cleanup();
    }
  });

  it("marks itself leaving so it fades out over the workspace", async () => {
    const view = await mountTestComponent(<StartupSplash phase="booting" leaving windowMaximized={false} onRestart={async () => undefined} />);
    try {
      assert.equal(view.container.querySelector('[data-testid="startup-splash"]')?.hasAttribute("data-leaving"), true);
    } finally {
      await view.cleanup();
    }
  });
});
