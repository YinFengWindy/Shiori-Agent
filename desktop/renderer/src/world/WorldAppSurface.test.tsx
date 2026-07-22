/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { WorldAppSurface } from "./WorldAppSurface";

describe("WorldAppSurface", () => {
  it("owns a full-window surface with a return route outside the desktop shell", () => {
    const markup = renderToStaticMarkup(<WorldAppSurface onExit={() => undefined}><div>世界内容</div></WorldAppSurface>);

    assert.match(markup, /world-app-surface/);
    assert.match(markup, /返回 Shiori/);
    assert.match(markup, /h-screen/);
  });
});
