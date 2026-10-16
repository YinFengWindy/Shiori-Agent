import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { siteVerificationMeta } from "../src/lib/siteVerification";

describe("siteVerificationMeta", () => {
  it("uses the public Baidu token by default and allows environment overrides or explicit omission", () => {
    assert.deepEqual(siteVerificationMeta({}), [
      { name: "baidu-site-verification", content: "codeva-DEC4knpJlo" },
    ]);
    assert.deepEqual(siteVerificationMeta({ SITE_VERIFY_GOOGLE: "  ", SITE_VERIFY_BING: "", SITE_VERIFY_BAIDU: " codeva-x " }), [
      { name: "baidu-site-verification", content: "codeva-x" },
    ]);
    assert.deepEqual(siteVerificationMeta({ SITE_VERIFY_BAIDU: "  " }), []);
  });
});
