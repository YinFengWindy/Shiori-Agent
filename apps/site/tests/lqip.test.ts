import assert from "node:assert/strict";
import { dirname, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import { LQIP_WIDTH, lqipDataUri } from "../src/lib/lqip";

const sprite = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../desktop/renderer/src/shared/assets/mascot/yinfeng-smug.webp",
);

describe("lqipDataUri", () => {
  it("shrinks a sprite to a tiny WebP data URI that keeps its aspect ratio and alpha", async () => {
    const uri = await lqipDataUri(sprite);
    const [, base64] = uri.match(/^data:image\/webp;base64,(.+)$/) ?? [];
    assert.ok(base64, `not a WebP data URI: ${uri.slice(0, 40)}`);
    assert.ok(uri.length <= 2048, `placeholder data URI is ${uri.length} characters`);
    const placeholder = await sharp(Buffer.from(base64, "base64")).metadata();
    const original = await sharp(sprite).metadata();
    assert.equal(placeholder.format, "webp");
    assert.equal(placeholder.width, LQIP_WIDTH);
    assert.equal(placeholder.height, Math.round((LQIP_WIDTH * original.height) / original.width));
    assert.equal(placeholder.hasAlpha, true);
  });
});
