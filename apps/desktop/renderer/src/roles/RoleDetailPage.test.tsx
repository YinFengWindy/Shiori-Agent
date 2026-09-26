import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleDetailPage } from "./RoleDetailPage";

type PageProps = Parameters<typeof RoleDetailPage>[0];

function renderPage(overrides: Partial<PageProps> = {}) {
  return renderToStaticMarkup(
    <RoleDetailPage
      activeRole={null}
      activeRoleId="role-1"
      bridgeReady
      previewAvatar={null}
      currentMood=""
      moodIllustrationUrl=""
      roleForm={createEmptyRoleForm()}
      roleFormDirty={false}
      savingRole={false}
      onBackToList={() => undefined}
      onGoToChat={() => undefined}
      onOpenAssetsPage={() => undefined}
      onOpenPluginSettings={() => undefined}
      onRoleModelChanged={() => undefined}
      onUpdateRoleForm={() => undefined}
      onResetRoleForm={() => undefined}
      onSaveRole={() => undefined}
      {...overrides}
    />,
  );
}

const profileForm: RoleFormState = {
  ...createEmptyRoleForm(),
  name: "Mira",
  profile: {
    character: {
      profile: "A meticulous archivist.",
      personality: "Calm and precise.",
      behavior_rules: "Keep focus.",
    },
  },
};

const role: RoleRecord = {
  id: "role-1", name: "Mira", description: "", system_prompt: "", runtime_config: {},
  avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null,
  illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {},
  created_at: "", updated_at: "",
};

describe("RoleDetailPage", () => {
  it("opens on the profile tab with the setting grouped into sections", () => {
    const markup = renderPage({ roleForm: profileForm, roleFormDirty: true });

    assert.match(markup, /资料/);
    assert.match(markup, /记忆/);
    assert.doesNotMatch(markup, /知识库/);
    assert.match(markup, /能力/);
    assert.match(markup, /主动推送/);
    assert.doesNotMatch(markup, /渠道绑定/);
    assert.match(markup, /aria-current="page"[^>]*>.*资料/);
    assert.match(markup, /角色设定/);
    assert.match(markup, /性格与规则/);
    assert.match(markup, /执行规则/);
    assert.doesNotMatch(markup, /data-testid="role-channel-config"/);
  });

  it("puts labeled 重置 and 保存 buttons in the header, off until the draft changes", () => {
    const clean = renderPage();
    assert.match(clean, /data-testid="save-role-button"[^>]*disabled=""[^>]*>.*保存<\/button>/);
    assert.match(clean, /data-testid="reset-role-button"[^>]*disabled=""[^>]*>.*重置<\/button>/);

    const dirty = renderPage({ roleFormDirty: true });
    assert.doesNotMatch(dirty, /data-testid="save-role-button"[^>]*disabled=""/);
    assert.doesNotMatch(dirty, /data-testid="reset-role-button"[^>]*disabled=""/);
  });

  it("keeps save unavailable while the bridge is down, and shows 保存中 while saving", () => {
    assert.match(renderPage({ roleFormDirty: true, bridgeReady: false }), /data-testid="save-role-button"[^>]*disabled=""/);
    const saving = renderPage({ roleFormDirty: true, savingRole: true });
    assert.match(saving, /data-testid="save-role-button"[^>]*data-saving="true"[^>]*disabled=""[^>]*>.*保存中…<\/button>/);
  });

  it("offers 去聊天 for a loaded role while the bridge is up", () => {
    assert.match(renderPage({ activeRole: role }), /data-testid="role-detail-go-to-chat"[^>]*>.*去聊天/);
    assert.doesNotMatch(renderPage({ activeRole: role }), /data-testid="role-detail-go-to-chat"[^>]*disabled/);
    assert.match(renderPage({ activeRole: role, bridgeReady: false }), /data-testid="role-detail-go-to-chat"[^>]*disabled=""/);
    assert.match(renderPage(), /data-testid="role-detail-go-to-chat"[^>]*disabled=""/);
  });

  it("shows the current mood and a visible 更换形象 action in the character header", () => {
    const markup = renderPage({ activeRole: role, currentMood: "平静" });
    assert.match(markup, /data-testid="role-detail-mood"[^>]*>.*平静/);
    assert.match(markup, /data-testid="open-role-assets-button"[^>]*>.*更换形象<\/button>/);
  });

  it("draws the mood portrait behind the header when there is one", () => {
    assert.match(renderPage({ moodIllustrationUrl: "asset://smile.png" }), /data-has-portrait="true"/);
    assert.match(renderPage(), /data-has-portrait="false"/);
  });

  it("shows the role's models on the profile tab for a loaded role", () => {
    assert.match(renderPage({ activeRole: role }), /data-testid="role-model-section"/);
    assert.match(renderPage({ activeRole: role }), /聊天模型/);
  });
});
