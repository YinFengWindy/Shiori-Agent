import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import { RoleCapabilitiesPanel } from "./RoleCapabilitiesPanel";

describe("RoleCapabilitiesPanel", () => {
  it("renders capability names and current state labels", () => {
    const markup = renderToStaticMarkup(<RoleCapabilitiesPanel activeRole={null} bridgeReady roleForm={{ ...createEmptyRoleForm(), nsfwMemoryEnabled: true }} onUpdate={() => undefined} />);

    assert.match(markup, /运行能力/);
    assert.match(markup, /已启用/);
    assert.doesNotMatch(markup, /桌宠/);
  });
});
