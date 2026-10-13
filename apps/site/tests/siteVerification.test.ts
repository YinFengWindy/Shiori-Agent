import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { siteVerificationMeta } from "../src/lib/siteVerification";

describe("siteVerificationMeta", () => {
  it("emits a tag only for engines with a token, blank ones counting as unset", () => {
    assert.deepEqual(siteVerificationMeta({}), []);
    assert.deepEqual(siteVerificationMeta({ SITE_VERIFY_GOOGLE: "  ", SITE_VERIFY_BING: "", SITE_VERIFY_BAIDU: " codeva-x " }), [
      { name: "baidu-site-verification", content: "codeva-x" },
    ]);
  });
});
