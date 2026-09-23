/// <reference types="node" />

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

// Deliberately not colocated inside site/assets/: `pnpm run build:site`
// scans that whole directory for the actual image imports, so a stray
// non-image file there would confuse that (unrelated) static analysis.
const assetsDir = resolve(dirname(fileURLToPath(import.meta.url)), "../assets");
const siteAssetsSourcePath = resolve(dirname(fileURLToPath(import.meta.url)), "siteAssets.ts");
const MAX_EDGE = 1920;
const METADATA_CHUNKS = new Set(["EXIF", "XMP ", "ICCP"]);
// VP8X feature flags (byte 0 of the chunk): ICC profile, alpha, EXIF, XMP.
const VP8X_ICC = 0x20;
const VP8X_ALPHA = 0x10;
const VP8X_EXIF = 0x08;
const VP8X_XMP = 0x04;
/** Cut-out standing sprites must keep their transparent background. */
const ALPHA_REQUIRED = /^sprite-\d+\.webp$/;

interface RiffChunk {
  tag: string;
  offset: number;
  size: number;
}

function readRiffChunks(data: Buffer): RiffChunk[] {
  const chunks: RiffChunk[] = [];
  let offset = 12; // past "RIFF" + size(4) + "WEBP"
  while (offset + 8 <= data.length) {
    const tag = data.toString("ascii", offset, offset + 4);
    const size = data.readUInt32LE(offset + 4);
    chunks.push({ tag, offset: offset + 8, size });
    offset += 8 + size + (size % 2);
  }
  return chunks;
}

/** Read the pixel dimensions out of a WebP's VP8 / VP8L / VP8X chunk. */
function readWebpDimensions(data: Buffer, chunks: RiffChunk[]): { width: number; height: number } {
  const vp8x = chunks.find((chunk) => chunk.tag === "VP8X");
  if (vp8x) {
    const d = data.subarray(vp8x.offset, vp8x.offset + vp8x.size);
    const width = (d[4] | (d[5] << 8) | (d[6] << 16)) + 1;
    const height = (d[7] | (d[8] << 8) | (d[9] << 16)) + 1;
    return { width, height };
  }
  const vp8l = chunks.find((chunk) => chunk.tag === "VP8L");
  if (vp8l) {
    const d = data.subarray(vp8l.offset, vp8l.offset + vp8l.size);
    assert.equal(d[0], 0x2f, "VP8L chunk must start with its 0x2F signature byte");
    const bits = d.readUInt32LE(1);
    const width = (bits & 0x3fff) + 1;
    const height = ((bits >> 14) & 0x3fff) + 1;
    return { width, height };
  }
  const vp8 = chunks.find((chunk) => chunk.tag === "VP8 ");
  if (vp8) {
    const d = data.subarray(vp8.offset, vp8.offset + vp8.size);
    // 3-byte frame tag, 3-byte start code (0x9d 0x01 0x2a), then two
    // little-endian 16-bit fields whose low 14 bits are width/height.
    assert.equal(d[3], 0x9d, "VP8 bitstream must start with its start code");
    assert.equal(d[4], 0x01);
    assert.equal(d[5], 0x2a);
    const width = d.readUInt16LE(6) & 0x3fff;
    const height = d.readUInt16LE(8) & 0x3fff;
    return { width, height };
  }
  throw new Error("no VP8/VP8L/VP8X chunk found");
}

/**
 * Whether the WebP carries an alpha channel: a lossless VP8L bitstream
 * (which always has an alpha bit), or an extended VP8X file whose alpha flag
 * is set and that actually contains an ALPH chunk or a VP8L bitstream.
 */
function hasAlpha(data: Buffer, chunks: RiffChunk[]): boolean {
  const vp8x = chunks.find((chunk) => chunk.tag === "VP8X");
  if (!vp8x) return chunks.some((chunk) => chunk.tag === "VP8L");
  const flagged = (data[vp8x.offset] & VP8X_ALPHA) !== 0;
  return flagged && chunks.some((chunk) => chunk.tag === "ALPH" || chunk.tag === "VP8L");
}

function listWebpFiles(): string[] {
  return readdirSync(assetsDir).filter((name) => name.endsWith(".webp"));
}

describe("site asset hygiene", () => {
  for (const file of listWebpFiles()) {
    describe(file, () => {
      const data = readFileSync(join(assetsDir, file));

      it("is a WebP file (RIFF/WEBP header)", () => {
        assert.equal(data.toString("ascii", 0, 4), "RIFF");
        assert.equal(data.toString("ascii", 8, 12), "WEBP");
      });

      it("has a longest edge <= 1920px", () => {
        const chunks = readRiffChunks(data);
        const { width, height } = readWebpDimensions(data, chunks);
        assert.ok(width > 0 && height > 0, `expected positive dimensions, got ${width}x${height}`);
        assert.ok(
          Math.max(width, height) <= MAX_EDGE,
          `${file} is ${width}x${height}, longest edge exceeds ${MAX_EDGE}px`,
        );
      });

      it("carries no EXIF/XMP/ICC metadata chunks", () => {
        const chunks = readRiffChunks(data);
        const found = chunks.map((chunk) => chunk.tag).filter((tag) => METADATA_CHUNKS.has(tag));
        assert.deepEqual(found, [], `${file} must not carry metadata chunks, found: ${found.join(", ")}`);
        const vp8x = chunks.find((chunk) => chunk.tag === "VP8X");
        if (vp8x) {
          const flags = data[vp8x.offset];
          assert.equal(flags & (VP8X_ICC | VP8X_EXIF | VP8X_XMP), 0, `${file} VP8X header must not declare ICC/EXIF/XMP`);
        }
      });

      if (ALPHA_REQUIRED.test(file)) {
        it("keeps its transparent background (alpha WebP)", () => {
          assert.ok(hasAlpha(data, readRiffChunks(data)), `${file} must be a WebP with alpha (VP8X+ALPH or VP8L)`);
        });
      }
    });
  }

  it("manifest only references files that exist on disk", () => {
    // Parsed as text rather than imported: siteAssets.ts statically imports
    // its WebP files (the reliable, well-supported Vite asset pattern), and
    // the plain Node test runner used by `pnpm test` has no loader for
    // binary image imports.
    const source = readFileSync(siteAssetsSourcePath, "utf8");
    const importPattern = /from "\.\.\/assets\/([^"]+\.webp)"/g;
    const referenced = [...source.matchAll(importPattern)].map((match) => match[1]);
    assert.ok(referenced.length > 0, "expected siteAssets.ts to import at least one asset");
    const onDisk = new Set(listWebpFiles());
    for (const fileName of referenced) {
      assert.ok(onDisk.has(fileName), `siteAssets.ts references missing asset: ${fileName}`);
    }
  });

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

  it("has a non-empty asset directory", () => {
    assert.ok(listWebpFiles().length > 0, "expected at least one .webp asset");
  });
});
