import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { inlineJson, softwareVersion } from "../src/lib/structuredData";

describe("inlineJson", () => {
  it("keeps text from closing the script element it sits in", () => {
    const json = inlineJson({ name: "</script><script>alert(1)</script>" });
    assert.ok(!json.includes("<"));
    assert.deepEqual(JSON.parse(json), { name: "</script><script>alert(1)</script>" });
  });
});

describe("softwareVersion", () => {
  it("drops a release tag's leading v, and only before a number", () => {
    assert.equal(softwareVersion("v0.5.3"), "0.5.3");
    assert.equal(softwareVersion("0.5.3"), "0.5.3");
    assert.equal(softwareVersion("vision-1"), "vision-1");
  });
});
