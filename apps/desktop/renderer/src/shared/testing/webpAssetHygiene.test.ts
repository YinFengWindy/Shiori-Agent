/// <reference types="node" />

import assert from "node:assert/strict";
import { it } from "node:test";
import { hasAlpha, readRiffChunks, VP8X_ALPHA } from "./webpAssetHygiene";

it("recognizes both alpha encodings and rejects an opaque file", () => {
  const riff = (...chunks: [string, Buffer][]) =>
    Buffer.concat([
      Buffer.from("RIFF\0\0\0\0WEBP", "ascii"),
      ...chunks.map(([tag, body]) => {
        const header = Buffer.alloc(8);
        header.write(tag, 0, "ascii");
        header.writeUInt32LE(body.length, 4);
        return Buffer.concat([header, body, Buffer.alloc(body.length % 2)]);
      }),
    ]);
  const vp8x = (flags: number) => Buffer.from([flags, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  const lossyWithAlpha = riff(["VP8X", vp8x(VP8X_ALPHA)], ["ALPH", Buffer.alloc(2)], ["VP8 ", Buffer.alloc(2)]);
  const lossless = riff(["VP8L", Buffer.alloc(6)]);
  const opaque = riff(["VP8 ", Buffer.alloc(2)]);
  const flagWithoutAlpha = riff(["VP8X", vp8x(VP8X_ALPHA)], ["VP8 ", Buffer.alloc(2)]);
  assert.equal(hasAlpha(lossyWithAlpha, readRiffChunks(lossyWithAlpha)), true);
  assert.equal(hasAlpha(lossless, readRiffChunks(lossless)), true);
  assert.equal(hasAlpha(opaque, readRiffChunks(opaque)), false);
  assert.equal(hasAlpha(flagWithoutAlpha, readRiffChunks(flagWithoutAlpha)), false);
});
