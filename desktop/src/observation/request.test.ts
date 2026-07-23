import assert from "node:assert/strict";
import test from "node:test";
import { requestObservationResult } from "./request.js";
import type { CapturedObservationFrame } from "./types.js";

const frame: CapturedObservationFrame = {
  frameId: "frame-1",
  capturedAt: "2026-07-23T12:00:00Z",
  width: 100,
  height: 80,
  scaleFactor: 1,
  imageBase64: "png",
};

test("observation requests allow one refresh and reject a repeated screenshot loop", async () => {
  let requestCount = 0;
  let captureCount = 0;
  const bridge = {
    invoke: async () => {
      requestCount += 1;
      return { payload: { request: "screenshot" }, error: null };
    },
  };

  await assert.rejects(
    requestObservationResult({
      bridge,
      roleId: "role-a",
      captureFrame: async () => {
        captureCount += 1;
        return frame;
      },
      previousResult: null,
      recentBubbles: [],
      isCurrent: () => true,
    }),
    /重复请求截图/,
  );
  assert.equal(requestCount, 2);
  assert.equal(captureCount, 2);
});
