import assert from "node:assert/strict";
import test from "node:test";
import { loadAvatarImage } from "./renderer";

test("aborting an image load clears its callbacks and rejects instead of accepting a late asset", async () => {
  class ImageStub { src = ""; onload: (() => void) | null = null; onerror: (() => void) | null = null; constructor() { images.push(this); } }
  const images: ImageStub[] = [], original = Object.getOwnPropertyDescriptor(globalThis, "Image");
  Object.defineProperty(globalThis, "Image", { configurable: true, value: ImageStub });
  try {
    const abort = new AbortController(), loading = loadAvatarImage("shiori-asset://image", abort.signal), rejected = assert.rejects(loading, { name: "AbortError" });
    abort.abort(); await rejected; assert.equal(images[0].src, ""); assert.equal(images[0].onload, null); assert.equal(images[0].onerror, null);
  } finally { if (original) Object.defineProperty(globalThis, "Image", original); else Reflect.deleteProperty(globalThis, "Image"); }
});
