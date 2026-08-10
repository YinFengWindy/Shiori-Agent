/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatLonelinessCooldownStatus } from "./chatStatus";

describe("formatLonelinessCooldownStatus", () => {
  it("formats an active cooldown in Beijing time", () => {
    assert.equal(
      formatLonelinessCooldownStatus(
        "2026-08-10T18:16:40+08:00",
        new Date("2026-08-10T18:03:00+08:00"),
      ),
      "冷却至 18:16",
    );
  });

  it("hides expired or invalid cooldowns", () => {
    const now = new Date("2026-08-10T18:17:00+08:00");
    assert.equal(formatLonelinessCooldownStatus("2026-08-10T18:16:40+08:00", now), "");
    assert.equal(formatLonelinessCooldownStatus("invalid", now), "");
  });
});
