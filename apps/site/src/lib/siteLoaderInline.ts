/**
 * The home page loader as one classic script (SiteLoader.astro). The retry
 * helpers are `imageRetry.runtime.js`, pasted in so a dropped first screen
 * does not depend on another file also surviving the CDN.
 *
 * `retryRuntime` is that file's text, including its `export` lines. Those
 * lines are removed here; a classic script cannot import.
 */
export function siteLoaderInlineScript(retryRuntime: string): string {
  const helpers = retryRuntime.replaceAll(/^export /gm, "").trim();
  return `(() => {
${helpers}
${LOADER_BODY}
})();`;
}

/**
 * Loader body. Runs after the helpers, inside the same function, so it
 * calls them by name. The cap is armed before any picture is fetched and
 * does not wait for a retry: once it sets `data-leaving`, further tries
 * are handed to the `<img>`.
 */
const LOADER_BODY = `  const loader = document.getElementById("site-loader");
  if (!loader) return;
  const root = document.documentElement;

  // Back / Forward or an anchor (the head's gate): no loader, the
  // pictures load straight into their places. Module scripts (the scene's
  // time-of-day swap of data-src) have run by DOMContentLoaded.
  if (root.hasAttribute("data-site-loader-skip")) {
    loader.remove();
    const show = () => {
      bindCriticalImages(document);
      for (const image of document.querySelectorAll("img[data-first-screen][data-src]")) image.src = image.dataset.src;
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", show, { once: true });
    else show();
    return;
  }

  // The illustration fades in over the wash once decoded (site.css).
  const art = loader.querySelector("[data-loader-art]");
  art?.decode().then(
    () => art.setAttribute("data-ready", ""),
    () => undefined,
  );
  // Hides 吟风 and the dialogue box until the reveal (site.css).
  root.dataset.siteLoader = "loading";

  // Keep the narrative still while the loader shows: wheel, touch, scroll
  // keys and clicks stop here (capture on window runs before its handlers).
  const SCROLL_KEYS = new Set([" ", "PageDown", "PageUp", "ArrowDown", "ArrowUp", "Home", "End"]);
  const block = (event) => {
    if (event.type === "keydown" && !SCROLL_KEYS.has(event.key)) return;
    if (event.cancelable && event.type !== "touchstart" && event.type !== "touchend") event.preventDefault();
    event.stopImmediatePropagation();
  };
  const guarded = [
    ["wheel", { capture: true, passive: false }],
    ["touchmove", { capture: true, passive: false }],
    ["touchstart", { capture: true, passive: true }],
    ["touchend", { capture: true, passive: true }],
    ["keydown", { capture: true }],
    ["click", { capture: true }],
  ];
  for (const [type, options] of guarded) window.addEventListener(type, block, options);

  // Both fades end in the loader's own animation: then it leaves for good.
  loader.addEventListener("animationend", (event) => {
    if (event.target !== loader) return;
    loader.remove();
    delete root.dataset.siteLoader;
    for (const [type, options] of guarded) window.removeEventListener(type, block, options);
  });

  const reveal = () => {
    if (loader.hasAttribute("data-leaving")) return;
    root.dataset.siteLoader = "revealing";
    loader.setAttribute("data-leaving", "");
  };

  // The cap, from navigation start: \`--site-loader-cap\` (also the CSS fallback's delay).
  // It is not waiting on a picture. A retry still in flight is handed to the img.
  const cap = getComputedStyle(loader).getPropertyValue("--site-loader-cap").trim();
  const capMs = cap.endsWith("ms") ? parseFloat(cap) : parseFloat(cap) * 1000;
  setTimeout(reveal, Math.max(0, capMs - performance.now()));

  const percent = loader.querySelector("[data-loader-percent]");
  let loaded = 0;
  let total = 0;
  const showProgress = () => {
    const share = total > 0 ? Math.min(1, loaded / total) : 0;
    loader.style.setProperty("--site-loader-progress", String(share));
    if (percent) percent.textContent = \`\${Math.floor(share * 100)}%\`;
  };

  // Download one picture, counting its bytes as they arrive, then hand it
  // to its <img> and decode it. The weight is the response's Content-Length,
  // the optimized file. A dropped download is tried again (imageRetry.runtime.js);
  // once the cap has revealed, the rest of those tries are the img's.
  const load = async (image) => {
    const url = image.dataset.src;
    if (!url) return;
    let weight = 0;
    let counted = 0;
    let attemptReceived = 0;
    const rollback = () => {
      if (counted > 0) loaded -= counted;
      if (weight > 0) total -= weight;
      counted = 0;
      weight = 0;
      attemptReceived = 0;
      showProgress();
    };
    const setWeight = (next) => {
      if (!next || next === weight) return;
      total += next - weight;
      weight = next;
      showProgress();
    };
    const count = (bytes) => {
      if (weight <= 0 || bytes <= 0) return;
      const add = Math.min(bytes, weight - counted);
      if (add <= 0) return;
      counted += add;
      loaded += add;
      showProgress();
    };
    const outcome = await fetchImageWithRetry(url, {
      priority: "high",
      shouldWait: () => !loader.hasAttribute("data-leaving"),
      onAttempt: (attempt) => {
        if (attempt > 0) rollback();
        attemptReceived = 0;
      },
      onProgress: (progress) => {
        setWeight(progress.total && progress.total > 0 ? progress.total : 1);
        count(progress.received - attemptReceived);
        attemptReceived = progress.received;
      },
    });
    if (outcome.ok) {
      const type = outcome.contentType ? { type: outcome.contentType } : undefined;
      image.src = URL.createObjectURL(new Blob([outcome.bytes], type));
    } else {
      image.dataset.imageRetries = String(outcome.retries);
      image.src = outcome.src;
      if (weight === 0) setWeight(1);
    }
    await image.decode().catch(() => undefined);
    count(weight);
  };

  // The backdrop and her current face, nothing else. Module scripts (the
  // scene's time-of-day swap of data-src) have run by DOMContentLoaded, so
  // the URLs read then are the ones that will show. Binding retries here,
  // after that swap, covers the backdrop and the loader art as well.
  const track = async () => {
    bindCriticalImages(document);
    const images = [...document.querySelectorAll("img[data-first-screen][data-src]")];
    await Promise.all(images.map((image) => load(image)));
    reveal();
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => void track(), { once: true });
  else void track();`;
