import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { PluginCatalogProvider } from "./PluginCatalogContext";
import { PluginNavigationHost } from "./PluginNavigationHost";
import { createPluginCatalog } from "./pluginCatalog";

const catalog = createPluginCatalog([
  {
    schema_version: 1,
    plugin_id: "novelai",
    name: "NovelAI",
    version: "1",
    description: "",
    author: "",
    capabilities: ["ui.navigation"],
    rpc_methods: [],
    ui_contributions: [
      { id: "image-studio", slot: "navigation", title: "图像生成", renderer: "novelai.image-studio", order: 40 },
      { id: "prompt-tags", slot: "navigation", title: "提示词库", renderer: "novelai.prompt-tags", order: 41 },
    ],
  },
]);

describe("PluginNavigationHost", () => {
  it("renders navigation only for loaded plugin contributions", () => {
    const loaded = renderToStaticMarkup(
      <PluginCatalogProvider catalog={catalog}>
        <PluginNavigationHost buttonClass="entry" onOpenImageStudio={() => undefined} onOpenPromptTagLibrary={() => undefined} />
      </PluginCatalogProvider>,
    );
    const absent = renderToStaticMarkup(
      <PluginNavigationHost buttonClass="entry" onOpenImageStudio={() => undefined} onOpenPromptTagLibrary={() => undefined} />,
    );
    assert.match(loaded, /图像生成/);
    assert.match(loaded, /提示词库/);
    assert.equal(absent, "");
  });
});
