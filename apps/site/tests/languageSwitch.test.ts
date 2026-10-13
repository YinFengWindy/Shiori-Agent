import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { anchorAtReadingLine, hrefWithAnchor } from "../src/lib/languageSwitch";

describe("anchorAtReadingLine", () => {
  const places = [
    { id: "memory", top: -800 },
    { id: "affection", top: 200 },
    { id: "proactive", top: 900 },
  ];

  it("names the last place whose top has risen to the reading line", () => {
    assert.equal(anchorAtReadingLine(places, 450), "affection");
    assert.equal(anchorAtReadingLine(places, 200), "affection");
    assert.equal(anchorAtReadingLine(places, 1000), "proactive");
  });

  it("names the first place while none has reached the line yet", () => {
    assert.equal(anchorAtReadingLine([{ id: "memory", top: 600 }, { id: "affection", top: 1400 }], 450), "memory");
  });

  it("rejects no places or a line it cannot place", () => {
    assert.throws(() => anchorAtReadingLine([], 450));
    assert.throws(() => anchorAtReadingLine(places, Number.NaN));
  });
});

describe("hrefWithAnchor", () => {
  it("adds the anchor to the switch's target, replacing any it had", () => {
    assert.equal(hrefWithAnchor("/en/", "remembers"), "/en/#remembers");
    assert.equal(hrefWithAnchor("/#download", "see-you"), "/#see-you");
  });
});
