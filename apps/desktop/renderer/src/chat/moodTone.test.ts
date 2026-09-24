/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { moodTone } from "./moodTone";

describe("moodTone", () => {
  it("maps the common Chinese mood words onto their tones", () => {
    assert.equal(moodTone("开心"), "happy");
    assert.equal(moodTone("很高兴"), "happy");
    assert.equal(moodTone("害羞"), "shy");
    assert.equal(moodTone("脸红心跳"), "shy");
    assert.equal(moodTone("难过"), "sad");
    assert.equal(moodTone("有点寂寞"), "sad");
    assert.equal(moodTone("生气"), "angry");
    assert.equal(moodTone("吃醋"), "angry");
    assert.equal(moodTone("平静"), "calm");
  });

  it("understands role-card emotion names case-insensitively", () => {
    assert.equal(moodTone("joy"), "happy");
    assert.equal(moodTone("Embarrassment"), "shy");
    assert.equal(moodTone("sadness"), "sad");
    assert.equal(moodTone("ANGER"), "angry");
    assert.equal(moodTone("neutral"), "calm");
  });

  it("prefers the sharper tone when a label mixes two", () => {
    assert.equal(moodTone("委屈生气"), "angry");
    assert.equal(moodTone("开心又害羞"), "shy");
  });

  it("falls back to calm for unknown or empty labels", () => {
    assert.equal(moodTone("困惑"), "calm");
    assert.equal(moodTone("   "), "calm");
    assert.equal(moodTone(""), "calm");
  });
});
