/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  nextStartupSplashCheckMs,
  selectStartupSplashPhase,
  startupSlowAfterMs,
  startupSplashMinMs,
  type StartupSplashInput,
} from "./startupSplashPhase";

const booting = (attemptElapsedMs: number, overrides: Partial<StartupSplashInput> = {}) =>
  selectStartupSplashPhase({ health: "connecting", settled: false, shown: false, firstAttempt: true, attemptElapsedMs, ...overrides });

describe("selectStartupSplashPhase", () => {
  it("greets at once, and remarks on a slow start after 8 seconds", () => {
    assert.equal(startupSplashMinMs, 3000);
    assert.equal(startupSlowAfterMs, 8000);
    assert.equal(booting(0), "booting");
    assert.equal(booting(startupSlowAfterMs - 1), "booting");
    assert.equal(booting(startupSlowAfterMs), "slow");
  });

  it("holds a quick first startup until 3 seconds after launch, but not a slower one", () => {
    const answered = { health: "online", settled: true, shown: true };
    assert.equal(booting(startupSplashMinMs - 1, answered), "booting");
    assert.equal(booting(startupSplashMinMs, answered), null);
  });

  it("does not hold the splash after 「重启连接」", () => {
    assert.equal(booting(0, { health: "online", settled: true, shown: true, firstAttempt: false }), null);
  });

  it("shows a failed startup at once, and stays up while it retries from its own button", () => {
    assert.equal(booting(0, { health: "offline" }), "failed");
    assert.equal(booting(0, { shown: true, firstAttempt: false }), "booting");
  });

  it("never comes back once the backend has answered", () => {
    assert.equal(booting(startupSlowAfterMs, { settled: true }), null);
    assert.equal(booting(0, { settled: true }), null);
    assert.equal(booting(0, { settled: true, health: "offline", shown: true, firstAttempt: false }), null);
  });
});

describe("nextStartupSplashCheckMs", () => {
  it("wakes up once per threshold, then stops", () => {
    assert.equal(nextStartupSplashCheckMs(0, false), startupSplashMinMs);
    assert.equal(nextStartupSplashCheckMs(startupSplashMinMs, false), startupSlowAfterMs);
    assert.equal(nextStartupSplashCheckMs(startupSlowAfterMs, false), null);
    assert.equal(nextStartupSplashCheckMs(0, true), startupSplashMinMs);
    assert.equal(nextStartupSplashCheckMs(startupSplashMinMs, true), null);
  });
});
