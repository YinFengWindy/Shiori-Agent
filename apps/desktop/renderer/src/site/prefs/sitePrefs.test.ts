/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  DEFAULT_SITE_PREFS,
  SITE_PREFS_STORAGE_KEY,
  readSitePrefs,
  writeSitePrefs,
  type PrefsStorage,
  type SitePrefs,
} from "./sitePrefs";

function memoryStorage(initial?: string): PrefsStorage & { value: string | null } {
  const storage = {
    value: initial ?? null,
    getItem: (key: string) => (key === SITE_PREFS_STORAGE_KEY ? storage.value : null),
    setItem: (key: string, value: string) => {
      if (key === SITE_PREFS_STORAGE_KEY) storage.value = value;
    },
  };
  return storage;
}

describe("site prefs", () => {
  it("defaults to muted, mid volumes and normal text speed", () => {
    assert.deepEqual(readSitePrefs(memoryStorage()), DEFAULT_SITE_PREFS);
    assert.equal(DEFAULT_SITE_PREFS.soundEnabled, false);
    assert.equal(DEFAULT_SITE_PREFS.textSpeed, "normal");
  });

  it("round-trips a write through one versioned JSON key", () => {
    const storage = memoryStorage();
    const prefs: SitePrefs = { bgmVolume: 10, sfxVolume: 95, textSpeed: "fast", soundEnabled: true };
    writeSitePrefs(storage, prefs);
    assert.deepEqual(readSitePrefs(storage), prefs);
    assert.equal(JSON.parse(storage.value ?? "").version, 1);
  });

  it("falls back to defaults for corrupt JSON, non-objects and other versions", () => {
    for (const raw of ["{not json", "null", "42", '"text"', JSON.stringify({ version: 2, bgmVolume: 5 })]) {
      assert.deepEqual(readSitePrefs(memoryStorage(raw)), DEFAULT_SITE_PREFS, raw);
    }
  });

  it("falls back to defaults when storage access throws", () => {
    const blocked: PrefsStorage = {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => undefined,
    };
    assert.deepEqual(readSitePrefs(blocked), DEFAULT_SITE_PREFS);
  });

  it("clamps out-of-range volumes and defaults invalid fields individually", () => {
    const raw = JSON.stringify({ version: 1, bgmVolume: 180, sfxVolume: -4, textSpeed: "warp", soundEnabled: "yes" });
    assert.deepEqual(readSitePrefs(memoryStorage(raw)), {
      ...DEFAULT_SITE_PREFS,
      bgmVolume: 100,
      sfxVolume: 0,
    });
    const nonNumeric = JSON.stringify({ version: 1, bgmVolume: "loud", sfxVolume: null, textSpeed: "slow" });
    assert.deepEqual(readSitePrefs(memoryStorage(nonNumeric)), { ...DEFAULT_SITE_PREFS, textSpeed: "slow" });
  });

  it("normalizes out-of-range values on write", () => {
    const storage = memoryStorage();
    const written = writeSitePrefs(storage, { ...DEFAULT_SITE_PREFS, bgmVolume: 250.4, sfxVolume: 33.6 });
    assert.equal(written.bgmVolume, 100);
    assert.equal(written.sfxVolume, 34);
    assert.deepEqual(readSitePrefs(storage), written);
  });
});
