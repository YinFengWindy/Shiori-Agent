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
        sectionLabel="模型"
        subsections={[{ id: "main", label: "主模型" }]}
        onReset={() => undefined}
        onSave={async () => undefined}
        onSubsectionChange={() => undefined}
      />,
    );

    assert.match(markup, /aria-label="保存并重启"[^>]*disabled=""/);
    assert.doesNotMatch(markup, /aria-label="设置子区"/);
  });

  it("renders the section title with the toolbar", () => {
    const markup = renderToStaticMarkup(
      <SettingsPageToolbar
        bridgeReady
        currentSubsectionId="main"
        isDirty={false}
        savePhase="idle"
        sectionLabel="模型"
        subsections={[{ id: "main", label: "主模型" }]}
        onReset={() => undefined}
        onSave={async () => undefined}
        onSubsectionChange={() => undefined}
      />,
    );

    assert.match(markup, /<h2[^>]*>模型<\/h2>/);
  });

  it("renders subsection navigation when multiple destinations are available", () => {
    const markup = renderToStaticMarkup(
      <SettingsPageToolbar
        bridgeReady
        currentSubsectionId="telegram"
        isDirty={false}
        savePhase="idle"
        sectionLabel="频道"
        subsections={[
          { id: "telegram", label: "Telegram" },
          { id: "qq", label: "QQ" },
        ]}
        onReset={() => undefined}
        onSave={async () => undefined}
        onSubsectionChange={() => undefined}
      />,
    );

    assert.match(markup, /aria-label="设置子区"/);
    assert.match(markup, /aria-current="page"[^>]*>Telegram/);
    assert.match(markup, />QQ</);
  });
});
