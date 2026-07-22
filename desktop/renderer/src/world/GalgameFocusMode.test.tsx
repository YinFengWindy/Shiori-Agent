/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { GalgameFocusMode } from "./GalgameFocusMode";
import { createSceneBeat } from "./testFixtures";

describe("GalgameFocusMode", () => {
  it("takes over the viewport with dialogue and always keeps an exit", () => {
    const markup = renderToStaticMarkup(<GalgameFocusMode worldName="雨港" beat={createSceneBeat({ isCritical: true })} onExit={() => undefined} onRedrawShot={() => undefined} />);
    assert.match(markup, /fixed inset-0/);
    assert.match(markup, />你终于来了。</);
    assert.match(markup, /aria-label="退出焦点模式"/);
    assert.match(markup, />返回工作台</);
    assert.doesNotMatch(markup, />暂停演出</);
  });
});
