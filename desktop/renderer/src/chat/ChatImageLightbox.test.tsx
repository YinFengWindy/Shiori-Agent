/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatImageLightbox } from "./ChatImageLightbox";

function renderLightbox(regenerating: boolean): string {
  return renderToStaticMarkup(
    <ChatImageLightbox
      canAddToAssetLibrary
      canGoToNext={false}
      canGoToPrevious={false}
      canLocateMessage
      canRegenerate
      imagePath="D:\\images\\scene.png"
      addingToAssetLibrary={false}
      regenerating={regenerating}
      open
      onAddToAssetLibrary={() => undefined}
      onClose={() => undefined}
      onGoToNext={() => undefined}
      onGoToPrevious={() => undefined}
      onLocateMessage={() => undefined}
      onRegenerate={() => undefined}
    />,
  );
}

describe("ChatImageLightbox", () => {
  it("exposes desktop image regeneration from the enlarged preview", () => {
    assert.match(renderLightbox(false), /aria-label="重新生成图片"/);
  });

  it("disables and animates regeneration while the selected image is running", () => {
    const markup = renderLightbox(true);

    assert.match(markup, /aria-label="重新生成图片"[^>]*disabled/);
    assert.match(markup, /animate-spin/);
  });
});
