import assert from "node:assert/strict";
import { test } from "node:test";
import type { RendererDiagnosticPayload } from "../../../src/bridge/shared";
import { reportBackgroundFailure } from "./backgroundDiagnostics";

test("a background failure reaches the host's desktop diagnostic log, not only the hidden console", (context) => {
  const reported: RendererDiagnosticPayload[] = [];
  const host = globalThis as { window?: unknown };
  const previous = host.window;
  host.window = { miraDesktop: { reportRendererDiagnostic: (payload: RendererDiagnosticPayload) => { reported.push(payload); } } };
  context.mock.method(console, "error", () => {});
  try {
    const failure = new Error("bridge 还没起来");
    reportBackgroundFailure("desktop_pet restore", failure);

    assert.deepEqual(reported, [{
      kind: "error",
      message: "[plugin-host] desktop_pet restore 失败: bridge 还没起来",
      stack: failure.stack,
    }]);
  } finally {
    host.window = previous;
  }
});
