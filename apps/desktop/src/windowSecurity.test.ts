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

    assert.match(policy, /img-src[^;]*shiori-asset:/);
    assert.doesNotMatch(policy, /script-src[^;]*'unsafe-inline'/);
    assert.match(policy, /script-src[^;]*shiori-plugin:/);
    assert.match(policy, /script-src[^;]*'sha256-/);
    assert.doesNotMatch(policy, /script-src[^;]*(unsafe-eval|file:|https:|data:|blob:)/);
    assert.match(policy, /connect-src 'self'/);
    assert.doesNotMatch(policy, /connect-src[^;]*shiori-asset:/);
    assert.match(policy, /object-src 'none'/);
  });

  it("allows the Vite preamble and exact websocket origin only in development", () => {
    const policy = buildDesktopContentSecurityPolicy("http://127.0.0.1:5178/");
    assert.match(policy, /script-src[^;]*'unsafe-inline'/);
    assert.match(policy, /connect-src 'self' ws:\/\/127\.0\.0\.1:5178/);
  });

  it("does not mix a hash/nonce source into the dev script-src, so 'unsafe-inline' actually applies", () => {
    // CSP 规范：script-src 里只要出现 hash 或 nonce 来源，'unsafe-inline' 就会被浏览器整体忽略。
    // 开发环境依赖 'unsafe-inline' 放行 Vite 注入的内联 preamble 脚本，
    // 一旦这里混入 sha256/nonce 来源，preamble 检测就会失败并导致白屏（回归详见 #298）。
    const policy = buildDesktopContentSecurityPolicy("http://127.0.0.1:5178/");
    const [scriptSrc] = /script-src[^;]*/.exec(policy) ?? [""];
    assert.doesNotMatch(scriptSrc, /'sha256-/);
    assert.doesNotMatch(scriptSrc, /'nonce-/);
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
    const result = windowOpenHandler({ url: "shiori-asset://local/token" });
    await Promise.resolve();

    assert.equal(blocked, true);
    assert.deepEqual(result, { action: "deny" });
    assert.deepEqual(opened, ["shiori-asset://local/token"]);
  });
});
