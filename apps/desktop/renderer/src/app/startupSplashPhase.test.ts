/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  nextStartupSplashCheckMs,
  selectStartupSplashPhase,
  startupSlowAfterMs,
  startupSplashDelayMs,
  type StartupSplashInput,
} from "./startupSplashPhase";

const booting = (attemptElapsedMs: number, overrides: Partial<StartupSplashInput> = {}) =>
  selectStartupSplashPhase({ health: "connecting", settled: false, shown: false, attemptElapsedMs, ...overrides });

describe("selectStartupSplashPhase", () => {
  it("shows nothing for a startup that answers within the delay, so it cannot flash", () => {
    assert.equal(booting(0), null);
    assert.equal(booting(startupSplashDelayMs - 1), null);
    assert.equal(booting(startupSplashDelayMs - 1, { health: "online" }), null);
  });

  it("greets after the delay, and remarks on a slow start after 8 seconds", () => {
    assert.equal(startupSplashDelayMs, 400);
    assert.equal(startupSlowAfterMs, 8000);
    assert.equal(booting(startupSplashDelayMs), "booting");
    assert.equal(booting(startupSlowAfterMs - 1), "booting");
    assert.equal(booting(startupSlowAfterMs), "slow");
  });

  it("shows a failed startup at once, and stays up while it retries from its own button", () => {
    assert.equal(booting(0, { health: "offline" }), "failed");
    assert.equal(booting(0, { shown: true }), "booting");
  });

  it("never comes back once the backend has answered", () => {
    assert.equal(booting(startupSlowAfterMs, { settled: true }), null);
    assert.equal(booting(0, { settled: true, health: "offline", shown: true }), null);
  });
});

describe("nextStartupSplashCheckMs", () => {
  it("wakes up once per threshold, then stops", () => {
    assert.equal(nextStartupSplashCheckMs(0), startupSplashDelayMs);
    assert.equal(nextStartupSplashCheckMs(startupSplashDelayMs), startupSlowAfterMs);
    assert.equal(nextStartupSplashCheckMs(startupSlowAfterMs), null);
  });
});
