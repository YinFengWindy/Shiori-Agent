import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { createPluginRpcClient, type PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { PluginHostServicesProvider } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { PromptTagLibraryPage } from "./PromptTagLibraryPage";

const noopClient: PluginRpcClient = { ...createPluginRpcClient("fixture"), call: async <T,>() => ({} as T) };

describe("PromptTagLibraryPage", () => {
  it("renders the tag library inside its dedicated page", () => {
    const markup = renderToStaticMarkup(
      <PluginHostServicesProvider services={desktopPluginHostServices}>
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
