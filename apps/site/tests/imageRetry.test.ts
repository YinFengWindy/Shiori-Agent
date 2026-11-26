import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, it } from "node:test";
import { runInNewContext } from "node:vm";
import { fileURLToPath } from "node:url";
import {
  CRITICAL_IMAGE_SELECTOR,
  IMAGE_RETRY_LIMIT,
  bindCriticalImages,
  bindImageRetry,
  fetchImageWithRetry,
  imageRetryUrl,
  type RetryableImage,
} from "../src/lib/imageRetry.runtime.js";
import { siteLoaderInlineScript } from "../src/lib/siteLoaderInline";
import { dist } from "./support/builtSite";

const runtime = readFileSync(fileURLToPath(new URL("../src/lib/imageRetry.runtime.js", import.meta.url)), "utf8");
const loaderScript = siteLoaderInlineScript(runtime);

function assertParses(source: string) {
  const file = join(mkdtempSync(join(tmpdir(), "shiori-loader-")), "loader.js");
  writeFileSync(file, source);
  const checked = spawnSync(process.execPath, ["--check", file], { encoding: "utf8" });
  assert.equal(checked.status, 0, checked.stderr);
}

interface Scheduled {
  delayMs: number;
  run: () => void;
}

function fakeImage(src: string, state?: { complete?: boolean; naturalWidth?: number; currentSrc?: string }): RetryableImage & { fail: () => void } {
  let onError: (() => void) | undefined;
  const image: RetryableImage & { fail: () => void } = {
    src,
    currentSrc: state?.currentSrc ?? "",
    complete: state?.complete ?? false,
    naturalWidth: state?.naturalWidth ?? 0,
    dataset: {},
    addEventListener(type, listener) {
      if (type !== "error") throw new Error(`unexpected event ${type}`);
      if (onError) throw new Error("a second error listener");
      onError = listener;
    },
    fail() {
      image.complete = true;
      image.naturalWidth = 0;
      image.currentSrc = image.src;
      onError?.();
    },
  };
  return image;
}

function bytesResponse(bytes: Uint8Array, init?: { status?: number; length?: number; type?: string }): Response {
  const headers = new Headers();
  if (init?.type) headers.set("content-type", init.type);
  if (init?.length !== undefined) headers.set("content-length", String(init.length));
  else headers.set("content-length", String(bytes.byteLength));
  const body = new Uint8Array(bytes).buffer;
  return new Response(body, { status: init?.status ?? 200, headers });
}

describe("image retry address", () => {
  it("keeps the first request and replaces r on later ones", () => {
    assert.equal(imageRetryUrl("/_astro/scene.webp", 0), "/_astro/scene.webp");
    assert.equal(imageRetryUrl("/_astro/scene.webp?x=1#top", 1), "/_astro/scene.webp?x=1&r=1#top");
    assert.equal(imageRetryUrl("/_astro/scene.webp?r=1&x=1#top", 2), "/_astro/scene.webp?x=1&r=2#top");
    assert.equal(IMAGE_RETRY_LIMIT, 3);
  });
});

describe("bindImageRetry", () => {
  it("reloads a failed picture three times, then stops", () => {
    const scheduled: Scheduled[] = [];
    const image = fakeImage("/_astro/scene.webp");
    bindImageRetry(image, { schedule: (run, delayMs) => scheduled.push({ delayMs, run }) });
    const delays: number[] = [];
    for (let attempt = 0; attempt < 4; attempt += 1) {
      image.fail();
      if (attempt === 3) {
        assert.equal(scheduled.length, 3);
        break;
      }
      assert.equal(scheduled.length, attempt + 1);
      const next = scheduled[attempt];
      assert.ok(next);
      delays.push(next.delayMs);
      next.run();
    }
    assert.deepEqual(delays, [200, 400, 800]);
    assert.equal(image.src, "/_astro/scene.webp?r=3");
  });

  it("retries a picture that failed before the listener was attached", () => {
    const scheduled: Scheduled[] = [];
    const image = fakeImage("/_astro/scene.webp", { complete: true, naturalWidth: 0, currentSrc: "/_astro/scene.webp" });
    bindImageRetry(image, { schedule: (run, delayMs) => scheduled.push({ delayMs, run }) });
    assert.equal(scheduled.length, 1);
    assert.equal(scheduled[0]?.delayMs, 200);
    scheduled[0]?.run();
    assert.equal(image.src, "/_astro/scene.webp?r=1");
  });

  it("does not request a blob or data url again, and a second bind does not double the first failure", () => {
    const scheduled: Scheduled[] = [];
    const schedule = (run: () => void, delayMs: number) => scheduled.push({ delayMs, run });
    const held = fakeImage("blob:https://www.windchant.online/pic");
    bindImageRetry(held, { schedule });
    held.fail();
    const inline = fakeImage("data:image/gif;base64,AAAA");
    bindImageRetry(inline, { schedule });
    inline.fail();
    const scene = fakeImage("/_astro/scene.webp");
    bindImageRetry(scene, { schedule });
    bindImageRetry(scene, { schedule });
    scene.fail();
    assert.equal(scheduled.length, 1);
  });

  it("binds scene backdrops and the first screen, not later event CGs", () => {
    const seen: string[] = [];
    const scene = fakeImage("/_astro/scene.webp");
    bindCriticalImages(
      {
        querySelectorAll(selector) {
          seen.push(selector);
          return [scene];
        },
      },
      { schedule: () => undefined },
    );
    assert.deepEqual(seen, [CRITICAL_IMAGE_SELECTOR]);
    assert.match(CRITICAL_IMAGE_SELECTOR, /data-scene-backdrop/);
    assert.match(CRITICAL_IMAGE_SELECTOR, /data-first-screen/);
    assert.match(CRITICAL_IMAGE_SELECTOR, /data-loader-art/);
    assert.doesNotMatch(CRITICAL_IMAGE_SELECTOR, /data-cg/);
  });
});

describe("fetchImageWithRetry", () => {
  it("asks again after a closed connection and after a short body, then keeps the full picture", async () => {
    const calls: string[] = [];
    const waits: number[] = [];
    const good = new Uint8Array([1, 2, 3, 4]);
    let attempt = 0;
    const outcome = await fetchImageWithRetry("/_astro/scene.webp", {
      wait: async (ms) => {
        waits.push(ms);
      },
      fetchImpl: async (url) => {
        calls.push(url);
        attempt += 1;
        if (attempt === 1) throw new Error("Remote end closed connection");
        if (attempt === 2) return bytesResponse(new Uint8Array([1]), { length: 4, type: "image/webp" });
        return bytesResponse(good, { type: "image/webp" });
      },
    });
    assert.deepEqual(calls, ["/_astro/scene.webp", "/_astro/scene.webp?r=1", "/_astro/scene.webp?r=2"]);
    assert.deepEqual(waits, [200, 400]);
    assert.equal(outcome.ok, true);
    if (outcome.ok) {
      assert.deepEqual([...outcome.bytes], [...good]);
      assert.equal(outcome.contentType, "image/webp");
    }
  });

  it("stops after three retries when every attempt fails", async () => {
    const calls: string[] = [];
    const outcome = await fetchImageWithRetry("/_astro/face.webp", {
      wait: async () => undefined,
      fetchImpl: async (url) => {
        calls.push(url);
        throw new Error("IncompleteRead");
      },
    });
    assert.equal(calls.length, 4);
    assert.equal(outcome.ok, false);
    if (!outcome.ok) {
      assert.equal(outcome.retries, 3);
      assert.equal(outcome.src, "/_astro/face.webp?r=3");
    }
  });

  it("does not sleep on the remaining tries once the loader has revealed", async () => {
    const waits: number[] = [];
    let fetches = 0;
    const handed = await fetchImageWithRetry("/_astro/scene.webp", {
      wait: async (ms) => {
        waits.push(ms);
      },
      shouldWait: () => fetches === 0,
      fetchImpl: async () => {
        fetches += 1;
        throw new Error("closed");
      },
    });
    assert.equal(fetches, 1);
    assert.deepEqual(waits, []);
    assert.equal(handed.ok, false);
    if (!handed.ok) assert.equal(handed.src, "/_astro/scene.webp?r=1");

    let lateFetches = 0;
    const skipped = await fetchImageWithRetry("/_astro/scene.webp", {
      shouldWait: () => false,
      fetchImpl: async () => {
        lateFetches += 1;
        throw new Error("closed");
      },
    });
    assert.equal(lateFetches, 0);
    assert.equal(skipped.ok, false);
    if (!skipped.ok) {
      assert.equal(skipped.src, "/_astro/scene.webp");
      assert.equal(skipped.retries, 0);
    }
  });
});

describe("home page loader script", () => {
  it("parses, and the pasted helpers are the runtime", () => {
    assertParses(loaderScript);
    const pasted = runInNewContext(
      `${runtime.replaceAll(/^export /gm, "")}\n({ imageRetryUrl, IMAGE_RETRY_LIMIT })`,
    ) as { imageRetryUrl: typeof imageRetryUrl; IMAGE_RETRY_LIMIT: number };
    assert.equal(pasted.imageRetryUrl("/_astro/scene.webp?r=1", 2), imageRetryUrl("/_astro/scene.webp?r=1", 2));
    assert.equal(pasted.IMAGE_RETRY_LIMIT, IMAGE_RETRY_LIMIT);
    assert.match(loaderScript, /hasAttribute\("data-site-loader-skip"\)\) \{\n {4}loader\.remove\(\)/);
  });

  it("reveals on the cap while a picture is still in flight", () => {
    const seen = runLoader({ cap: "0s", fetchImpl: () => new Promise(() => undefined) });
    const cap = seen.timers.find((timer) => timer.ms === 0);
    assert.ok(cap, "the cap was not armed");
    assert.equal(seen.fetches.length, 1);
    cap.run();
    assert.equal(seen.leaving, true);
    assert.equal(seen.fetches.length, 1);
  });

  it("retries a dropped first-screen picture, then reveals", async () => {
    let attempt = 0;
    const seen = runLoader({
      cap: "10s",
      fetchImpl: async (url) => {
        attempt += 1;
        if (attempt === 1) throw new Error("closed");
        assert.equal(url, "/_astro/scene.webp?r=1");
        return bytesResponse(new Uint8Array([9, 9]), { type: "image/webp" });
      },
    });
    for (let i = 0; i < 10; i += 1) await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(seen.fetches, ["/_astro/scene.webp"]);
    const pause = seen.timers.find((timer) => timer.ms === 200);
    assert.ok(pause, "no backoff");
    pause.run();
    for (let i = 0; i < 20; i += 1) await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(seen.fetches, ["/_astro/scene.webp", "/_astro/scene.webp?r=1"]);
    assert.equal(seen.image.src, "blob:first-screen");
    assert.equal(seen.leaving, true);
    assert.equal(seen.timers.some((timer) => timer.ms === 10000 && timer.ran), false);
  });

  it("on a visit without the loader, still gives the first screen its address", () => {
    const seen = runLoader({ skip: true, cap: "10s", fetchImpl: async () => { throw new Error("should not fetch"); } });
    assert.equal(seen.removed, true);
    assert.equal(seen.image.src, "/_astro/scene.webp");
    assert.deepEqual(seen.fetches, []);
  });

  it("the built home page ships this script", () => {
    for (const page of ["index.html", "en/index.html"]) {
      const html = dist.read(page);
      const script = html.match(/<div id="site-loader"[\s\S]*?<script>([\s\S]*?)<\/script>/)?.[1] ?? "";
      assert.equal(script.trim(), loaderScript.trim(), page);
    }
  });
});

interface SeenLoader {
  timers: { ms: number; ran: boolean; run: () => void }[];
  fetches: string[];
  image: { src: string };
  leaving: boolean;
  removed: boolean;
}

function runLoader(options: {
  skip?: boolean;
  cap: string;
  fetchImpl: (url: string) => Promise<Response>;
}): SeenLoader {
  const fetches: string[] = [];
  const timers: { ms: number; ran: boolean; run: () => void }[] = [];
  const attributes = new Set<string>();
  const image = {
    src: "",
    currentSrc: "",
    complete: false,
    naturalWidth: 0,
    dataset: { src: "/_astro/scene.webp" } as Record<string, string | undefined>,
    addEventListener() {},
    decode: () => Promise.resolve(),
  };
  let removed = false;
  const loader = {
    remove() {
      removed = true;
    },
    hasAttribute: (name: string) => attributes.has(name),
    setAttribute: (name: string) => attributes.add(name),
    addEventListener() {},
    querySelector: () => null,
    style: { setProperty() {} },
  };
  const root = {
    dataset: {} as Record<string, string | undefined>,
    hasAttribute: (name: string) => (options.skip === true && name === "data-site-loader-skip"),
  };
  const sandbox = {
    document: {
      readyState: "complete",
      documentElement: root,
      getElementById: () => loader,
      querySelectorAll: () => [image],
      addEventListener() {},
    },
    window: { addEventListener() {}, removeEventListener() {} },
    getComputedStyle: () => ({ getPropertyValue: () => options.cap }),
    performance: { now: () => 0 },
    setTimeout: (fn: () => void, ms: number) => {
      const timer = { ms, ran: false, run: () => { timer.ran = true; fn(); } };
      timers.push(timer);
      return timers.length;
    },
    fetch: async (url: string) => {
      fetches.push(url);
      return options.fetchImpl(url);
    },
    URL: { createObjectURL: () => "blob:first-screen" },
    Blob,
    Uint8Array,
    Response,
    console,
  };
  runInNewContext(loaderScript, sandbox);
  return {
    timers,
    fetches,
    image,
    get leaving() {
      return attributes.has("data-leaving");
    },
    get removed() {
      return removed;
    },
  };
}
