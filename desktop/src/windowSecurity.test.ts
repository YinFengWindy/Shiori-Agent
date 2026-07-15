/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  attachDesktopWindowSecurity,
  buildDesktopContentSecurityPolicy,
  registerDesktopContentSecurityPolicy,
  resolveRendererEntryUrl,
  validateRendererDevServerUrl,
} from "./windowSecurity";

describe("renderer URL policy", () => {
  it("accepts only loopback HTTP Vite origins", () => {
    assert.equal(validateRendererDevServerUrl("http://127.0.0.1:5173/"), "http://127.0.0.1:5173/");
    assert.equal(validateRendererDevServerUrl("http://localhost:4173/"), "http://localhost:4173/");
    assert.throws(() => validateRendererDevServerUrl("https://example.com/"), /Untrusted/);
    assert.throws(() => validateRendererDevServerUrl("http://192.168.1.10:5173/"), /Untrusted/);
    assert.throws(() => validateRendererDevServerUrl("http://127.0.0.1/"), /Untrusted/);
  });

  it("uses an exact file URL for production", () => {
    const entryUrl = resolveRendererEntryUrl("C:\\app\\renderer-dist\\index.html", undefined);
    assert.match(entryUrl, /^file:/);
  });
});

describe("desktop CSP", () => {
  it("allows images but does not allow fetching the asset scheme", () => {
    const policy = buildDesktopContentSecurityPolicy(undefined);

    assert.match(policy, /img-src[^;]*mira-asset:/);
    assert.doesNotMatch(policy, /script-src[^;]*'unsafe-inline'/);
    assert.match(policy, /connect-src 'self'/);
    assert.doesNotMatch(policy, /connect-src[^;]*mira-asset:/);
    assert.match(policy, /object-src 'none'/);
  });

  it("allows the Vite preamble and exact websocket origin only in development", () => {
    const policy = buildDesktopContentSecurityPolicy("http://127.0.0.1:5178/");
    assert.match(policy, /script-src 'self' 'unsafe-inline'/);
    assert.match(policy, /connect-src 'self' ws:\/\/127\.0\.0\.1:5178/);
  });

  it("sets CSP only on main-frame responses", () => {
    let listener: ((details: {
      resourceType?: string;
      responseHeaders?: Record<string, string[]>;
    }, callback: (response: { responseHeaders?: Record<string, string[]> }) => void) => void) | null = null;
    registerDesktopContentSecurityPolicy({
      onHeadersReceived(nextListener) {
        listener = nextListener;
      },
    }, undefined);
    assert.ok(listener);
    let responseHeaders: Record<string, string[]> | undefined;
    listener({ resourceType: "mainFrame", responseHeaders: { Existing: ["value"] } }, (response) => {
      responseHeaders = response.responseHeaders;
    });

    assert.deepEqual(responseHeaders?.Existing, ["value"]);
    assert.ok(responseHeaders?.["Content-Security-Policy"]?.[0]);
  });
});

describe("desktop window security", () => {
  it("blocks cross-origin navigation and all child windows", async () => {
    let navigationHandler: ((event: { preventDefault(): void }, url: string) => void) | null = null;
    let windowOpenHandler: ((details: { url: string }) => { action: "deny" }) | null = null;
    const opened: string[] = [];
    attachDesktopWindowSecurity({
      on(_event, handler) {
        navigationHandler = handler;
      },
      setWindowOpenHandler(handler) {
        windowOpenHandler = handler;
      },
    }, {
      rendererEntryUrl: "http://127.0.0.1:5173/",
      openLocalAttachment(url) {
        opened.push(url);
      },
    });
    assert.ok(navigationHandler);
    assert.ok(windowOpenHandler);
    let blocked = false;

    navigationHandler({ preventDefault: () => { blocked = true; } }, "https://example.com/");
    const result = windowOpenHandler({ url: "mira-asset://local/token" });
    await Promise.resolve();

    assert.equal(blocked, true);
    assert.deepEqual(result, { action: "deny" });
    assert.deepEqual(opened, ["mira-asset://local/token"]);
  });
});
