import assert from "node:assert/strict";
import test from "node:test";
import {
  observationEpisodeIdleBoundaryMs,
  observationEpisodeMaximumMs,
  reduceObservationEpisode,
} from "./episode.js";
import type { ObservationResult } from "./types.js";

function result(capturedAt: string, activityKey: string, experienceCandidate: string): ObservationResult {
  return {
    frameId: capturedAt,
    capturedAt,
    width: 100,
    height: 100,
    scaleFactor: 1,
    interfaceSummary: "",
    activityKey,
    targets: [],
    risks: [],
    bubble: "",
    experienceCandidate,
  };
}

test("experience episodes stay together until activity changes", () => {
  const first = reduceObservationEpisode(null, result("2026-07-23T12:00:00Z", "writing", "一起写报告"), 0);
  const updated = reduceObservationEpisode(first.current, result("2026-07-23T12:20:00Z", "writing", "一起修改报告"), 1);
  assert.equal(updated.settled, null);
  assert.equal(updated.current?.summary, "一起写报告；一起修改报告");

  const switched = reduceObservationEpisode(updated.current, result("2026-07-23T12:30:00Z", "debugging", "一起排查错误"), 1);
  assert.equal(switched.settled?.summary, "一起写报告；一起修改报告");
  assert.equal(switched.current?.activityKey, "debugging");
});

test("experience episodes settle at the ninety-minute cap", () => {
  const start = Date.parse("2026-07-23T12:00:00Z");
  const first = reduceObservationEpisode(null, result(new Date(start).toISOString(), "writing", "开始写报告"), 0);
  const capped = reduceObservationEpisode(
    first.current,
    result(new Date(start + observationEpisodeMaximumMs).toISOString(), "writing", "继续写报告"),
    1,
  );
  assert.equal(capped.settled?.summary, "开始写报告");
  assert.equal(capped.current?.index, 1);
});

test("experience episodes settle after a substantial observation gap", () => {
  const start = Date.parse("2026-07-23T12:00:00Z");
  const first = reduceObservationEpisode(null, result(new Date(start).toISOString(), "writing", "开始写报告"), 0);
  const resumed = reduceObservationEpisode(
    first.current,
    result(new Date(start + observationEpisodeIdleBoundaryMs).toISOString(), "writing", "回来继续写报告"),
    1,
  );

  assert.equal(resumed.settled?.summary, "开始写报告");
  assert.equal(resumed.current?.summary, "回来继续写报告");
});
