/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  appearancePrefsStorageKey,
  defaultAppearancePrefs,
  parseAppearancePrefs,
  readAppearancePrefs,
  writeAppearancePrefs,
} from "./appearancePrefs";

function memoryStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    values,
  };
}

describe("appearance prefs", () => {
  it("turns the background motion on by default", () => {
    assert.equal(defaultAppearancePrefs.backdropMotion, true);
    assert.deepEqual(readAppearancePrefs(memoryStorage()), { backdropMotion: true });
  });

  it("persists a change and reads it back", () => {
    const storage = memoryStorage();
    assert.deepEqual(writeAppearancePrefs(storage, { backdropMotion: false }), { backdropMotion: false });
    assert.deepEqual(JSON.parse(storage.values.get(appearancePrefsStorageKey)!), { version: 1, backdropMotion: false });
    assert.deepEqual(readAppearancePrefs(storage), { backdropMotion: false });
  });

  it("falls back to the defaults for corrupt, foreign or mistyped values", () => {
    assert.deepEqual(parseAppearancePrefs("{not json"), defaultAppearancePrefs);
    assert.deepEqual(parseAppearancePrefs(JSON.stringify({ version: 99, backdropMotion: false })), defaultAppearancePrefs);
    assert.deepEqual(parseAppearancePrefs(JSON.stringify({ version: 1, backdropMotion: "no" })), defaultAppearancePrefs);
    assert.deepEqual(parseAppearancePrefs("null"), defaultAppearancePrefs);
  });
});
