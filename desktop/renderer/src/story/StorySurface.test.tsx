/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StorySurface } from "./StorySurface";

describe("StorySurface", () => {
  it("provides one shared Story backdrop and full-width panel shell", () => {
    const markup = renderToStaticMarkup(<StorySurface dataTestId="story-test" panelTestId="story-test-panel"><div>内容</div></StorySurface>);

    assert.match(markup, /data-testid="story-test"/);
    assert.match(markup, /data-testid="story-test-backdrop"/);
    assert.match(markup, /data-testid="story-test-panel"/);
    assert.match(markup, /min-h-full w-full/);
    assert.match(markup, /border-y border-\[#DDA9BE\]\/75/);
  });
});
