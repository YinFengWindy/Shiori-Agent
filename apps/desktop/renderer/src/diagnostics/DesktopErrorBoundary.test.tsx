import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { DesktopErrorBoundary } from "./DesktopErrorBoundary";

test("crash fallback opens the log folder and discloses scrubbed diagnostics", async (context) => {
  context.mock.method(console, "error", () => undefined);
  const view = await mountTestComponent(null);
  let opens = 0;
  Object.assign(window, { miraDesktop: {
    reportRendererDiagnostic: () => { throw new Error("log write failed"); },
    openDiagnosticsFolder: async () => { opens += 1; throw new Error("shell denied token=private-value"); },
  } });
  function Broken(): never { throw new Error("crash token=private-value"); }
  try {
    await view.render(<DesktopErrorBoundary><Broken /></DesktopErrorBoundary>);
    assert.match(view.container.textContent ?? "", /界面暂时不可用/);
    assert.doesNotMatch(view.container.textContent ?? "", /crash|已经记录/);
    const buttons = () => Array.from(view.container.querySelectorAll("button"));
    await act(async () => buttons().find((button) => button.textContent === "打开日志文件夹")?.click());
    assert.equal(opens, 1);
    assert.match(view.container.textContent ?? "", /日志文件夹打开失败/);
    await act(async () => buttons().find((button) => button.textContent?.includes("详情"))?.click());
    assert.match(view.container.textContent ?? "", /crash|shell denied/);
    assert.doesNotMatch(view.container.textContent ?? "", /private-value/);
  } finally { await view.cleanup(); }
});
