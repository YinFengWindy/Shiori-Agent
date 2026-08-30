/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { normalizeExternalLink, openExternalLink } from "./externalLinks";

describe("external link policy", () => {
  it("allows http, https, and mailto links", () => {
    assert.equal(normalizeExternalLink(" https://example.com/docs?q=1 "), "https://example.com/docs?q=1");
    assert.equal(normalizeExternalLink("http://localhost:3000/"), "http://localhost:3000/");
    assert.equal(normalizeExternalLink("mailto:hello@example.com"), "mailto:hello@example.com");
  });

  it("rejects executable, relative, and malformed links", () => {
    assert.equal(normalizeExternalLink("javascript:alert(1)"), null);
    assert.equal(normalizeExternalLink("data:text/html,<script>alert(1)</script>"), null);
    assert.equal(normalizeExternalLink("/settings"), null);
    assert.equal(normalizeExternalLink("not a url"), null);
  });

  it("does not invoke the operating system for rejected links", async () => {
    let opened = false;
    const result = await openExternalLink("javascript:alert(1)", async () => { opened = true; });
    assert.deepEqual(result, { ok: false, error: "external link protocol is not authorized" });
    assert.equal(opened, false);
  });
});
