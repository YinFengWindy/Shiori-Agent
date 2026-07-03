/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { captureRoleDetailScrollTop, restoreRoleDetailScrollTop } from "./roleDetailScrollState";

describe("captureRoleDetailScrollTop", () => {
  it("returns the current scrollTop when a container is present", () => {
    assert.equal(captureRoleDetailScrollTop({ scrollTop: 184 }), 184);
  });

  it("returns null when the scroll container is missing", () => {
    assert.equal(captureRoleDetailScrollTop(null), null);
  });
});

describe("restoreRoleDetailScrollTop", () => {
  it("writes the captured scrollTop back to the container", () => {
    const container = { scrollTop: 32 };

    const result = restoreRoleDetailScrollTop(container, 184);

    assert.equal(container.scrollTop, 184);
    assert.equal(result, null);
  });

  it("does nothing when there is no pending scroll offset", () => {
    const container = { scrollTop: 32 };

    const result = restoreRoleDetailScrollTop(container, null);

    assert.equal(container.scrollTop, 32);
    assert.equal(result, null);
  });
});
