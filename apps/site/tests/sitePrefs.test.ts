import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parseSoundEnabled, serializeSoundPrefs } from "../src/lib/sitePrefs";

describe("site sound preference", () => {
  it("starts muted without a valid stored choice", () => {
    for (const raw of [null, "", "not json", "null", "true", '{"soundEnabled":true}', '{"version":2,"soundEnabled":true}', '{"version":1,"soundEnabled":"yes"}']) {
      assert.equal(parseSoundEnabled(raw), false, `stored ${raw}`);
    }
  });

  it("keeps a choice stored by the old galgame site", () => {
    const oldSiteValue = '{"version":1,"bgmVolume":60,"sfxVolume":70,"textSpeed":"normal","soundEnabled":true}';
    assert.equal(parseSoundEnabled(oldSiteValue), true);
  });

  it("reads back what it stores", () => {
    assert.equal(parseSoundEnabled(serializeSoundPrefs(true)), true);
    assert.equal(parseSoundEnabled(serializeSoundPrefs(false)), false);
  });
});
