import assert from "node:assert/strict";
import { test } from "node:test";
import { emotionNameError, updateEmotionReference } from "./emotionReferenceState";

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
