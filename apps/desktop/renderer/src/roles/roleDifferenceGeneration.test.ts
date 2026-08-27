import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  applyRoleDifferenceProgress,
  createRoleDifferenceGenerationState,
} from "./roleDifferenceGeneration";

describe("roleDifferenceGeneration", () => {
  it("advances only trusted stages and marks a finished job successful", () => {
    const started = applyRoleDifferenceProgress(
      createRoleDifferenceGenerationState(),
      {
        job_id: "job-1",
        phase: "completed",
        current: "happy",
        completed: 2,
        stages: [
          { id: "neutral", status: "completed", error: "" },
          { id: "happy", status: "completed", error: "" },
          { id: "unknown", status: "completed", error: "" },
        ],
      },
    );

    assert.equal(started.status, "running");
    assert.equal(started.jobId, "job-1");
    assert.deepEqual(started.stages.slice(0, 2).map((stage) => stage.status), ["completed", "completed"]);
    assert.equal(started.stages.length, 5);

    const finished = applyRoleDifferenceProgress(started, {
      phase: "finished",
      completed: 5,
      category_name: "AI 差分",
    });
    assert.equal(finished.status, "success");
    assert.equal(finished.categoryName, "AI 差分");
  });
});
