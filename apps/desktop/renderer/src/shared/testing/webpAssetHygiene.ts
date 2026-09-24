/// <reference types="node" />

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";

const METADATA_CHUNKS = new Set(["EXIF", "XMP ", "ICCP"]);
// VP8X feature flags (byte 0 of the chunk): ICC profile, alpha, EXIF, XMP.
const VP8X_ICC = 0x20;
/** VP8X alpha flag, exported for fixtures that build synthetic files. */
export const VP8X_ALPHA = 0x10;
const VP8X_EXIF = 0x08;
const VP8X_XMP = 0x04;

/** One RIFF chunk of a WebP file. */
export interface RiffChunk {
  tag: string;
  offset: number;
  size: number;
}

/** Splits a WebP file into its RIFF chunks. */
export function readRiffChunks(data: Buffer): RiffChunk[] {
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

/** Reads the pixel dimensions out of a WebP's VP8 / VP8L / VP8X chunk. */
export function readWebpDimensions(data: Buffer, chunks: RiffChunk[]): { width: number; height: number } {
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
export function hasAlpha(data: Buffer, chunks: RiffChunk[]): boolean {
  const vp8x = chunks.find((chunk) => chunk.tag === "VP8X");
  if (!vp8x) return chunks.some((chunk) => chunk.tag === "VP8L");
  const flagged = (data[vp8x.offset] & VP8X_ALPHA) !== 0;
  return flagged && chunks.some((chunk) => chunk.tag === "ALPH" || chunk.tag === "VP8L");
}

/** Hygiene rules for one directory of committed WebP images. */
export interface WebpAssetRules {
  /** Directory holding the images (only `*.webp` files are checked). */
  dir: string;
  /** Longest allowed edge for a file. */
  maxEdge: (file: string) => number;
  /** Files that must keep a transparent background. */
  alphaRequired: (file: string) => boolean;
  /** Source module whose static image imports must all exist, parsed as text. */
  manifest: { path: string; importPattern: RegExp };
}

/**
 * Registers the WebP hygiene suite for one asset directory: real WebP,
 * size budget, no EXIF/XMP/ICC, alpha where required, and a manifest whose
 * imports all resolve. The manifest is parsed as text because the plain Node
 * test runner has no loader for binary image imports.
 */
export function describeWebpAssetHygiene(name: string, rules: WebpAssetRules) {
  const files = readdirSync(rules.dir).filter((file) => file.endsWith(".webp"));
  describe(name, () => {
    it("has a non-empty asset directory", () => {
      assert.ok(files.length > 0, "expected at least one .webp asset");
    });
    for (const file of files) {
      describe(file, () => {
        const data = readFileSync(join(rules.dir, file));
        it("is a WebP file (RIFF/WEBP header)", () => {
          assert.equal(data.toString("ascii", 0, 4), "RIFF");
          assert.equal(data.toString("ascii", 8, 12), "WEBP");
        });
        const maxEdge = rules.maxEdge(file);
        it(`has a longest edge <= ${maxEdge}px`, () => {
          const { width, height } = readWebpDimensions(data, readRiffChunks(data));
          assert.ok(width > 0 && height > 0, `expected positive dimensions, got ${width}x${height}`);
          assert.ok(Math.max(width, height) <= maxEdge, `${file} is ${width}x${height}, longest edge exceeds ${maxEdge}px`);
        });
        it("carries no EXIF/XMP/ICC metadata chunks", () => {
          const chunks = readRiffChunks(data);
          const found = chunks.map((chunk) => chunk.tag).filter((tag) => METADATA_CHUNKS.has(tag));
          assert.deepEqual(found, [], `${file} must not carry metadata chunks, found: ${found.join(", ")}`);
          const vp8x = chunks.find((chunk) => chunk.tag === "VP8X");
          if (vp8x) assert.equal(data[vp8x.offset] & (VP8X_ICC | VP8X_EXIF | VP8X_XMP), 0, `${file} VP8X header must not declare ICC/EXIF/XMP`);
        });
        if (rules.alphaRequired(file)) {
          it("keeps its transparent background (alpha WebP)", () => {
            assert.ok(hasAlpha(data, readRiffChunks(data)), `${file} must be a WebP with alpha (VP8X+ALPH or VP8L)`);
          });
        }
      });
    }
    it("manifest only references files that exist on disk", () => {
      const source = readFileSync(rules.manifest.path, "utf8");
      const referenced = [...source.matchAll(rules.manifest.importPattern)].map((match) => match[1]);
      assert.ok(referenced.length > 0, "expected the manifest to import at least one asset");
      for (const file of referenced) assert.ok(files.includes(file), `manifest references missing asset: ${file}`);
    });
  });
}
