/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { affectionUiRegistry, useChatAffectionContribution, useRoleAffectionContribution } from "./affectionUiRegistry";

function Slots() {
  const role = useRoleAffectionContribution();
  const chat = useChatAffectionContribution();
  return <span>{`${role?.pluginId ?? "-"}|${chat?.pluginId ?? "-"}`}</span>;
}

const Empty = () => null;

describe("affectionUiRegistry", () => {
  it("clears both slots when the plugin unregisters", () => {
    affectionUiRegistry.registerRole({ pluginId: "affection", Component: Empty });
    affectionUiRegistry.registerChat({ pluginId: "affection", Component: Empty });
    try {
      assert.equal(renderToStaticMarkup(<Slots />), "<span>affection|affection</span>");
    } finally {
      affectionUiRegistry.unregister("affection");
    }
    assert.equal(renderToStaticMarkup(<Slots />), "<span>-|-</span>");
  });
});
