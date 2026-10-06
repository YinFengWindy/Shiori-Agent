import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { test } from "node:test";
import { bindNativeDocumentLifecycle } from "./lifecycle";

test("actual document reload, crash and destruction release resources; frames and same-document navigation do not", () => {
  const source = new EventEmitter(); let released = 0;
  bindNativeDocumentLifecycle(source, () => { released++; });
  source.emit("did-start-navigation", { isMainFrame: false, isSameDocument: false });
  source.emit("did-start-navigation", { isMainFrame: true, isSameDocument: true });
  assert.equal(released, 0);
  source.emit("did-start-navigation", { isMainFrame: true, isSameDocument: false });
  source.emit("render-process-gone"); source.emit("destroyed");
  assert.equal(released, 3);
});
