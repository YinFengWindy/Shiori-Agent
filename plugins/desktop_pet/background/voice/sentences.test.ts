import assert from "node:assert/strict";
import { test } from "node:test";
import { SpeechSentenceBuffer, spokenText } from "./sentences";

test("streamed speech waits for complete sentences and strips non-spoken actions and code", () => {
  const buffer = new SpeechSentenceBuffer();
  assert.deepEqual(buffer.push("（微笑）你好"), []);
  assert.deepEqual(buffer.push("！下一句"), ["你好！"]);
  assert.deepEqual(buffer.push("", true), ["下一句"]);
  assert.equal(spokenText("[链接](https://example.test) ```js\nalert(1)``` 😊"), "链接");
});
