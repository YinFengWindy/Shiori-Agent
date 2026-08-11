import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import { RoleCapabilitiesPanel } from "./RoleCapabilitiesPanel";
import { PluginCatalogProvider } from "../plugins/PluginCatalogContext";
import { createPluginCatalog } from "../plugins/pluginCatalog";

const capabilityCatalog = createPluginCatalog([
  {
    schema_version: 1,
    plugin_id: "desktop_pet",
    name: "桌宠",
    version: "1.0.0",
    description: "",
    author: "",
    capabilities: ["ui.role_capability"],
    rpc_methods: [],
    ui_contributions: [{ id: "desktop-pet", slot: "role-capability", title: "桌宠", renderer: "desktop-pet.role-capability", order: 50 }],
  },
]);

describe("RoleCapabilitiesPanel", () => {
  it("renders compact capability rows with state labels instead of a wrapping card", () => {
    const markup = renderToStaticMarkup(
      <PluginCatalogProvider catalog={capabilityCatalog}>
        <RoleCapabilitiesPanel activeRole={null} bridgeReady roleForm={{ ...createEmptyRoleForm(), nsfwMemoryEnabled: true }} onUpdate={() => undefined} />
      </PluginCatalogProvider>,
    );

    assert.match(markup, /运行能力/);
    assert.match(markup, /已启用/);
    assert.match(markup, /未配置桌宠/);
    assert.match(markup, /divide-y divide-\[#E7ECF1\]/);
    assert.doesNotMatch(markup, /shadow-\[0_12px_30px/);
  });

  it("omits plugin capabilities when their manifests are absent", () => {
    const markup = renderToStaticMarkup(<RoleCapabilitiesPanel activeRole={null} bridgeReady roleForm={createEmptyRoleForm()} onUpdate={() => undefined} />);
    assert.doesNotMatch(markup, /自动场景 CG/);
    assert.doesNotMatch(markup, /未配置桌宠/);
  });
});
