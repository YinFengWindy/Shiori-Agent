import assert from "node:assert/strict";
import { test } from "node:test";
import type { RoleVoice } from "../shared/contracts";
import { emotionNameError, pendingCatalogMoods, setVoiceReference, updateEmotionReference, voiceReference } from "./emotionReferenceState";

test("private emotion names reject empty, duplicate and prototype keys", () => {
  for (const name of ["", "  ", " happy ", "__proto__", "constructor", "prototype", "toString", "hasOwnProperty", "line\nfeed"]) assert.ok(emotionNameError(name, ["happy"]), name);
  assert.equal(emotionNameError(" 难过 ", ["happy"]), "");
  assert.ok(emotionNameError("extra", Array.from({ length: 64 }, (_, index) => String(index))));
});

test("reference changes and deletion preserve other private mappings without inherited entries", () => {
  const reference = { asset: "a.wav", prompt_text: "参考", prompt_lang: "zh" } as const;
  const original = { happy: reference };
  const updated = updateEmotionReference(original, "sad", { ...reference, asset: "b.wav" });
  assert.deepEqual(Object.keys(updateEmotionReference(updated, "happy", null)), ["sad"]);
  assert.deepEqual(original, { happy: reference });
});

test("the empty mood addresses the default reference and never an inherited mapping", () => {
  const reference = { asset: "a.wav", prompt_text: "", prompt_lang: "zh" } as const;
  const voice: RoleVoice = { text_lang: "auto", speed: 1, default: null, moods: {} };
  const withDefault = setVoiceReference(voice, "", reference);
  assert.deepEqual(withDefault, { ...voice, default: reference });
  assert.equal(voiceReference(withDefault, ""), reference);
  assert.equal(voiceReference(withDefault, "toString"), null);
  assert.deepEqual(setVoiceReference(withDefault, "开心", reference).moods, { 开心: reference });
});

test("catalog moods without audio are offered once, skipping configured and unusable names", () => {
  assert.deepEqual(pendingCatalogMoods([" 开心", "开心", "平静", "constructor", ""], ["平静"]), ["开心"]);
});
