import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import { RoleDetailPage } from "./RoleDetailPage";

describe("RoleDetailPage", () => {
  it("opens on the profile tab while retaining unified save controls", () => {
    const markup = renderToStaticMarkup(
      <RoleDetailPage
        activeIllustration=""
        activeRole={null}
        activeRoleId="role-1"
        bridgeReady
        previewAvatar={null}
        chatBackgroundUrl=""
        roleForm={{ ...createEmptyRoleForm(), name: "Mira", systemPrompt: "Keep focus." }}
        roleFormDirty
        savingRole={false}
        onBackToList={() => undefined}
        onOpenAssetsPage={() => undefined}
        onUpdateRoleForm={() => undefined}
        onResetRoleForm={() => undefined}
        onSaveRole={() => undefined}
      />,
    );

    assert.match(markup, /资料/);
    assert.match(markup, /能力/);
    assert.match(markup, /渠道与主动推送/);
    assert.match(markup, /aria-current="page"[^>]*>.*资料/);
    assert.match(markup, /data-testid="edit-role-prompt"/);
    assert.match(markup, /data-has-featured-image="false"/);
    assert.match(markup, /resize-none overflow-hidden/);
    assert.doesNotMatch(markup, /data-testid="role-channel-config"/);
    assert.match(markup, /data-testid="save-role-button"/);
  });

  it("keeps save unavailable until the draft has changes and the bridge is ready", () => {
    const markup = renderToStaticMarkup(
      <RoleDetailPage
        activeIllustration=""
        activeRole={null}
        activeRoleId="role-1"
        bridgeReady={false}
        previewAvatar={null}
        chatBackgroundUrl=""
        roleForm={createEmptyRoleForm()}
        roleFormDirty={false}
        savingRole={false}
        onBackToList={() => undefined}
        onOpenAssetsPage={() => undefined}
        onUpdateRoleForm={() => undefined}
        onResetRoleForm={() => undefined}
        onSaveRole={() => undefined}
      />,
    );

    assert.match(markup, /data-testid="save-role-button"[^>]*disabled=""/);
  });
});
