import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { PluginHostServicesProvider } from "@shiori/sdk";
import { createFakeHostServices, createFakePluginClient } from "@shiori/sdk/testing";
import { PromptTagLibraryPage } from "./PromptTagLibraryPage";

const noopClient = createFakePluginClient({ call: async <T,>() => ({} as T) });

describe("PromptTagLibraryPage", () => {
  it("renders the tag library inside its dedicated page", () => {
    const markup = renderToStaticMarkup(
      <PluginHostServicesProvider services={createFakeHostServices().host}>
        <PromptTagLibraryPage
          client={noopClient}
          bridgeReady={false}
          section="list"
          onOpenSection={() => undefined}
        />
      </PluginHostServicesProvider>,
    );

    assert.match(markup, /data-testid="prompt-tag-library-page"/);
    assert.match(markup, /data-testid="prompt-tag-library"/);
  });
});
