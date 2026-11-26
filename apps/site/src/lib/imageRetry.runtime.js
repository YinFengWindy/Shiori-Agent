/**
 * Retries for pictures the mainland CDN sometimes drops on the way back
 * from Vercel: the connection closes, or the body arrives short.
 * The home page loader inlines this file so the first screen does not
 * wait on a second download.
 */

/** How many times to ask again after the first failure. */
export const IMAGE_RETRY_LIMIT = 3;

/**
 * Scene backdrops, the narrative's first frame, and the loader illustration.
 * Later faces and event CGs stay off this list: a miss there is not the
 * first screen, and the narrative fetches them as that line comes up.
 */
export const CRITICAL_IMAGE_SELECTOR = "img[data-scene-backdrop], img[data-first-screen], img[data-loader-art]";

/** The picture's own address, without an `r` this file added on an earlier try. */
function stripRetryParam(url) {
  const hashAt = url.indexOf("#");
  const hash = hashAt >= 0 ? url.slice(hashAt) : "";
  const withoutHash = hashAt >= 0 ? url.slice(0, hashAt) : url;
  const queryAt = withoutHash.indexOf("?");
  if (queryAt < 0) return url;
  const path = withoutHash.slice(0, queryAt);
  const kept = withoutHash
    .slice(queryAt + 1)
    .split("&")
    .filter((part) => part.length > 0 && part !== "r" && !part.startsWith("r="));
  return `${path}${kept.length > 0 ? `?${kept.join("&")}` : ""}${hash}`;
}

/**
 * Address for attempt `attempt`. 0 is the URL as written, so the hashed
 * path stays the cache key. Later attempts set `r` and replace an earlier
 * `r`, so a failed response is not reused and the query does not grow.
 * @param {string} url
 * @param {number} attempt
 * @returns {string}
 */
export function imageRetryUrl(url, attempt) {
  if (!Number.isInteger(attempt) || attempt < 0) throw new Error(`image attempt ${attempt} is not a whole number`);
  const base = stripRetryParam(url);
  if (attempt === 0) return base;
  const hashAt = base.indexOf("#");
  const hash = hashAt >= 0 ? base.slice(hashAt) : "";
  const withoutHash = hashAt >= 0 ? base.slice(0, hashAt) : base;
  const joiner = withoutHash.includes("?") ? "&" : "?";
  return `${withoutHash}${joiner}r=${attempt}${hash}`;
}

/**
 * Pause before retry `retry` (1, then 2, then 3): 200ms, 400ms, 800ms.
 * @param {number} retry
 * @returns {number}
 */
export function imageRetryDelayMs(retry) {
  if (!Number.isInteger(retry) || retry < 1) throw new Error(`image retry ${retry} is not a later attempt`);
  return 200 * 2 ** (retry - 1);
}

/**
 * The next try after a failure, or `undefined` once the limit is spent.
 * @param {{ retries: number, src: string }} failed
 * @param {number} [limit]
 * @returns {{ retries: number, src: string, delayMs: number } | undefined}
 */
export function nextImageRetry(failed, limit = IMAGE_RETRY_LIMIT) {
  if (!Number.isInteger(failed.retries) || failed.retries < 0) {
    throw new Error(`image retry count ${failed.retries} is not a whole number`);
  }
  if (failed.retries >= limit) return undefined;
  const retries = failed.retries + 1;
  return { retries, src: imageRetryUrl(failed.src, retries), delayMs: imageRetryDelayMs(retries) };
}

/**
 * Download `url`. A closed connection, a bad status, or a body shorter
 * than Content-Length is another try, up to the limit. Once `shouldWait`
 * is false the loader has started to leave, so the next address is
 * returned instead of being slept on.
 * @param {string} url
 * @param {{
 *   limit?: number,
 *   priority?: "high" | "low" | "auto",
 *   fetchImpl?: (url: string, init?: { priority?: string }) => Promise<Response>,
 *   wait?: (ms: number) => Promise<void>,
 *   shouldWait?: () => boolean,
 *   onAttempt?: (attempt: number) => void,
 *   onProgress?: (progress: { total: number | undefined, received: number }) => void,
 * }} [options]
 * @returns {Promise<
 *   { ok: true, bytes: Uint8Array, contentType: string } |
 *   { ok: false, src: string, retries: number }
 * >}
 */
export async function fetchImageWithRetry(url, options = {}) {
  const limit = options.limit ?? IMAGE_RETRY_LIMIT;
  const fetchImpl = options.fetchImpl ?? fetch;
  const wait = options.wait ?? ((ms) => new Promise((resolve) => { setTimeout(resolve, ms); }));
  const shouldWait = options.shouldWait ?? (() => true);
  let retries = 0;
  while (retries <= limit) {
    const src = imageRetryUrl(url, retries);
    if (retries > 0) {
      // The loader's own cap already revealed the page: do not sit here.
      if (!shouldWait()) return { ok: false, src, retries };
      await wait(imageRetryDelayMs(retries));
      if (!shouldWait()) return { ok: false, src, retries };
    } else if (!shouldWait()) {
      return { ok: false, src, retries };
    }
    try {
      options.onAttempt?.(retries);
      const response = await fetchImpl(src, options.priority ? { priority: options.priority } : undefined);
      if (!response.ok || !response.body) throw new Error(`${src}: ${response.status}`);
      const length = Number(response.headers.get("content-length"));
      const total = Number.isFinite(length) && length > 0 ? length : undefined;
      const reader = response.body.getReader();
      const chunks = [];
      let received = 0;
      options.onProgress?.({ total, received });
      for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) {
        chunks.push(chunk.value);
        received += chunk.value.byteLength;
        options.onProgress?.({ total, received });
      }
      // A clean end that is still short of Content-Length is the dropped body.
      if (total !== undefined && received < total) throw new Error(`${src}: truncated`);
      const bytes = new Uint8Array(received);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
      }
      return { ok: true, bytes, contentType: response.headers.get("content-type") ?? "" };
    } catch {
      if (retries >= limit) return { ok: false, src, retries };
      retries += 1;
    }
  }
  throw new Error("image retry ended without a result");
}

/**
 * On `error`, load the picture again after a short pause, at most the
 * limit. A picture that already failed before this listener existed is
 * picked up too. Blob and data URLs are bytes the loader already holds.
 * @param {HTMLImageElement} image
 * @param {{ limit?: number, schedule?: (callback: () => void, delayMs: number) => void }} [options]
 */
export function bindImageRetry(image, options = {}) {
  if (image.dataset.imageRetryBound) return;
  image.dataset.imageRetryBound = "1";
  const limit = options.limit ?? IMAGE_RETRY_LIMIT;
  const schedule = options.schedule ?? ((callback, delayMs) => { setTimeout(callback, delayMs); });
  const retry = () => {
    const src = image.currentSrc || image.src;
    if (!src || src.startsWith("blob:") || src.startsWith("data:")) return;
    if (image.dataset.imageRetryPending) return;
    const retries = Number(image.dataset.imageRetries || "0");
    if (!Number.isInteger(retries) || retries < 0) return;
    const next = nextImageRetry({ retries, src }, limit);
    if (!next) return;
    image.dataset.imageRetries = String(next.retries);
    image.dataset.imageRetryPending = "1";
    schedule(() => {
      delete image.dataset.imageRetryPending;
      image.src = next.src;
    }, next.delayMs);
  };
  image.addEventListener("error", retry);
  // Parsed images can fail before this script runs; `error` does not fire again.
  if (image.complete && image.naturalWidth === 0 && (image.currentSrc || image.src)) retry();
}

/**
 * Scene backdrops and the other first-screen pictures under `root`.
 * @param {ParentNode} root
 * @param {{ limit?: number, schedule?: (callback: () => void, delayMs: number) => void }} [options]
 */
export function bindCriticalImages(root, options) {
  for (const image of root.querySelectorAll(CRITICAL_IMAGE_SELECTOR)) bindImageRetry(image, options);
}
