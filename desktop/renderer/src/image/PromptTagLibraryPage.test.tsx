import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { PromptTagLibraryPage } from "./PromptTagLibraryPage";

describe("PromptTagLibraryPage", () => {
  it("renders as a dedicated page with a return action", () => {
    const markup = renderToStaticMarkup(
      <PromptTagLibraryPage
        bridgeReady={false}
        section="list"
        onOpenSection={() => undefined}
      />,
    );

    assert.match(markup, /data-testid="prompt-tag-library-page"/);
    assert.match(markup, /素材列表/);
    assert.match(markup, /data-testid="prompt-tag-library"/);
  });
});
