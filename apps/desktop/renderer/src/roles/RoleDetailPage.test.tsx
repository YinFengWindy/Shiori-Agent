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
        roleForm={{
          ...createEmptyRoleForm(),
          name: "Mira",
          profile: {
            character: {
              profile: "A meticulous archivist.",
              personality: "Calm and precise.",
              behavior_rules: "Keep focus.",
            },
            knowledge_base: { enabled: true, entries: [] },
          },
        }}
        roleFormDirty
        savingRole={false}
        onBackToList={() => undefined}
        onGoToChat={() => undefined}
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
    assert.match(markup, /角色设定/);
    assert.match(markup, /性格/);
    assert.match(markup, /执行规则/);
    assert.doesNotMatch(markup, /data-testid="role-card-profile-knowledge"/);
    assert.doesNotMatch(markup, /data-testid="edit-role-prompt"/);
    assert.match(markup, /data-has-featured-image="false"/);
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
        onGoToChat={() => undefined}
        onOpenAssetsPage={() => undefined}
        onUpdateRoleForm={() => undefined}
        onResetRoleForm={() => undefined}
        onSaveRole={() => undefined}
      />,
    );

    assert.match(markup, /data-testid="save-role-button"[^>]*disabled=""/);
  });

  it("offers 去聊天 for a loaded role while the bridge is up", () => {
    const render = (bridgeReady: boolean, activeRole: Parameters<typeof RoleDetailPage>[0]["activeRole"]) => renderToStaticMarkup(
      <RoleDetailPage
        activeIllustration=""
        activeRole={activeRole}
        activeRoleId="role-1"
        bridgeReady={bridgeReady}
        previewAvatar={null}
        chatBackgroundUrl=""
        roleForm={createEmptyRoleForm()}
        roleFormDirty={false}
        savingRole={false}
        onBackToList={() => undefined}
        onGoToChat={() => undefined}
        onOpenAssetsPage={() => undefined}
        onUpdateRoleForm={() => undefined}
        onResetRoleForm={() => undefined}
        onSaveRole={() => undefined}
      />,
    );
    const role = { id: "role-1", name: "Mira" } as Parameters<typeof RoleDetailPage>[0]["activeRole"];
    assert.match(render(true, role), /data-testid="role-detail-go-to-chat"[^>]*>.*去聊天/);
    assert.doesNotMatch(render(true, role), /data-testid="role-detail-go-to-chat"[^>]*disabled/);
    assert.match(render(false, role), /data-testid="role-detail-go-to-chat"[^>]*disabled=""/);
    assert.match(render(true, null), /data-testid="role-detail-go-to-chat"[^>]*disabled=""/);
  });
});
