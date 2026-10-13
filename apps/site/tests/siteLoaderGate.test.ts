import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { SITE_LOADER_SKIP_ATTRIBUTE, shouldShowSiteLoader, siteLoaderGateScript } from "../src/lib/siteLoaderGate";
import { runLoaderGate } from "./support/loaderGate";

describe("shouldShowSiteLoader", () => {
  it("plays the loader on a plain visit: a link, a typed address, a reload", () => {
    for (const navigationType of ["navigate", "reload", undefined]) {
      assert.equal(shouldShowSiteLoader({ navigationType, hash: "" }), true, String(navigationType));
    }
  });

  it("leaves it out on Back / Forward, wherever the page was left", () => {
    assert.equal(shouldShowSiteLoader({ navigationType: "back_forward", hash: "" }), false);
    assert.equal(shouldShowSiteLoader({ navigationType: "back_forward", hash: "#download" }), false);
  });

  it("leaves it out when the address names a place on the page", () => {
    assert.equal(shouldShowSiteLoader({ navigationType: "navigate", hash: "#download" }), false);
    assert.equal(shouldShowSiteLoader({ navigationType: "reload", hash: "#download" }), false);
  });
});

describe("siteLoaderGateScript", () => {
  it("marks <html> exactly when the loader stays out, in a context with nothing but the browser's globals", () => {
    assert.deepEqual(runLoaderGate(siteLoaderGateScript, { navigationType: "navigate", hash: "" }), []);
    assert.deepEqual(runLoaderGate(siteLoaderGateScript, { navigationType: undefined, hash: "" }), []);
    assert.deepEqual(runLoaderGate(siteLoaderGateScript, { navigationType: "back_forward", hash: "" }), [SITE_LOADER_SKIP_ATTRIBUTE]);
    assert.deepEqual(runLoaderGate(siteLoaderGateScript, { navigationType: "navigate", hash: "#download" }), [SITE_LOADER_SKIP_ATTRIBUTE]);
  });
});
