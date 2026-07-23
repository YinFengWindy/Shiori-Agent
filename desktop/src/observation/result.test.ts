import assert from "node:assert/strict";
import test from "node:test";
import {
  isScreenshotObservationRequest,
  parseObservationResult,
} from "./result.js";
import type { CapturedObservationFrame } from "./types.js";

const frame: CapturedObservationFrame = {
  frameId: "frame-1",
  capturedAt: "2026-07-23T12:00:00Z",
  width: 1000,
  height: 800,
  scaleFactor: 1.25,
  imageBase64: "png",
};

function observationPayload(overrides: Record<string, unknown> = {}) {
  return {
    frame_id: frame.frameId,
    captured_at: frame.capturedAt,
    width: frame.width,
    height: frame.height,
    scale_factor: frame.scaleFactor,
    interface_summary: "编辑器",
    activity_key: "writing",
    targets: [],
    risks: [],
    bubble: "还差一点就完成了",
    experience_candidate: "下午一起整理报告",
    ...overrides,
  };
}

test("observation result validation rejects mismatched frames and invalid risks", () => {
  assert.throws(
    () => parseObservationResult(observationPayload({ frame_id: "other-frame" }), frame),
    /请求帧不一致/,
  );
  assert.throws(
    () => parseObservationResult(observationPayload({ risks: ["unknown"] }), frame),
    /风险结构无效/,
  );
});

test("observation protocol accepts only an exact screenshot refresh request", () => {
  assert.equal(isScreenshotObservationRequest({ request: "screenshot" }), true);
  assert.equal(isScreenshotObservationRequest({ request: "click" }), false);
  assert.equal(isScreenshotObservationRequest({ request: "screenshot", x: 1 }), false);
});
