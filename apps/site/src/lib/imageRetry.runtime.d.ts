/** How many times to ask again after the first failure. */
export const IMAGE_RETRY_LIMIT: number;

/** Scene backdrops, the first frame, and the loader illustration. */
export const CRITICAL_IMAGE_SELECTOR: string;

/** Address for attempt `attempt`. 0 keeps the URL that was written. */
export function imageRetryUrl(url: string, attempt: number): string;

/** Pause before retry `retry` (1-based), in milliseconds. */
export function imageRetryDelayMs(retry: number): number;

/** The next try after a failure, or `undefined` once the limit is spent. */
export function nextImageRetry(
  failed: { readonly retries: number; readonly src: string },
  limit?: number,
): { readonly retries: number; readonly src: string; readonly delayMs: number } | undefined;

export type ImageFetchOutcome =
  | { readonly ok: true; readonly bytes: Uint8Array; readonly contentType: string }
  | { readonly ok: false; readonly src: string; readonly retries: number };

/** Download `url`, retrying a dropped connection or a short body up to the limit. */
export function fetchImageWithRetry(
  url: string,
  options?: {
    readonly limit?: number;
    readonly priority?: "high" | "low" | "auto";
    readonly fetchImpl?: (url: string, init?: { priority?: string }) => Promise<Response>;
    readonly wait?: (ms: number) => Promise<void>;
    /** False once the loader has started to leave: do not sleep on the next try. */
    readonly shouldWait?: () => boolean;
    readonly onAttempt?: (attempt: number) => void;
    readonly onProgress?: (progress: { total: number | undefined; received: number }) => void;
  },
): Promise<ImageFetchOutcome>;

/** A picture element the retry listener can drive. Tests use a stand-in; the page passes an `<img>`. */
export interface RetryableImage {
  src: string;
  currentSrc: string;
  complete: boolean;
  naturalWidth: number;
  dataset: Record<string, string | undefined>;
  addEventListener(type: "error", listener: () => void): void;
}

/** On `error`, load `image` again after a short pause, at most the limit. */
export function bindImageRetry(
  image: RetryableImage,
  options?: {
    readonly limit?: number;
    readonly schedule?: (callback: () => void, delayMs: number) => void;
  },
): void;

/** Scene backdrops and the other first-screen pictures under `root`. */
export function bindCriticalImages(
  root: { querySelectorAll(selector: string): Iterable<RetryableImage> },
  options?: {
    readonly limit?: number;
    readonly schedule?: (callback: () => void, delayMs: number) => void;
  },
): void;
