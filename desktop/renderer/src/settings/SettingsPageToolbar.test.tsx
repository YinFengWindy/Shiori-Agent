/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { SettingsPageToolbar } from "./SettingsPageToolbar.js";

describe("SettingsPageToolbar", () => {
  it("disables save while the current draft is being persisted", () => {
    const markup = renderToStaticMarkup(
      <SettingsPageToolbar
        bridgeReady
        currentSubsectionId="main"
        isDirty
        savePhase="saving"
        subsections={[{ id: "main", label: "主模型" }]}
        onReset={() => undefined}
        onSave={async () => undefined}
        onSubsectionChange={() => undefined}
      />,
    );

    assert.match(markup, /aria-label="保存并重启"[^>]*disabled=""/);
    assert.match(markup, /<option value="main" selected="">主模型<\/option>/);
  });
});
