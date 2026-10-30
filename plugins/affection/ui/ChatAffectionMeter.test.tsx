import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatAffectionMeter } from "./ChatAffectionMeter";

describe("ChatAffectionMeter", () => {
  it("shows only the stage and a thin bar of its place on the whole range", () => {
    const markup = renderToStaticMarkup(<ChatAffectionMeter summary={{ value: 65, stage: "亲密", progress: 0.25, floor: 60 }} />);
    assert.match(markup, /data-testid="chat-affection"/);
    assert.match(markup, />亲密</);
    assert.match(markup, /width:82.5%/);
    assert.ok(!/>[^<]*\d[^<]*</.test(markup));
  });

  it("renders nothing for a malformed summary", () => {
    assert.equal(renderToStaticMarkup(<ChatAffectionMeter summary={{ value: Number.NaN, stage: "陌生", progress: 0, floor: null }} />), "");
  });
});
