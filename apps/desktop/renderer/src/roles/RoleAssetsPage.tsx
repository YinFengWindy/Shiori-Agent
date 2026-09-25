import { useState } from "react";
import { toFileUrl } from "../shared/format";
import { BackIcon } from "../shared/icons";
import { cx, iconButtonClass } from "../shared/styles";
import type { RoleAssetCategory, RoleFormState, RoleRecord } from "../shared/types";
import { confirmPersonaLines } from "../shared/mascot/mascotLines";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import { useRoleAssetsPanels } from "../plugins/useRoleAssetsPanels";
import { RoleAssetCategoryGroups } from "./RoleAssetCategoryGroups";
import { currentRoleAsset, resolveRoleAssetPreview, type RoleAssetMode } from "./roleAssetPreview";
import { RoleAssetPreviewPane } from "./RoleAssetPreviewPane";
import { applyMoodToIllustration, getMoodForIllustration } from "./roleMoodBindingSelection";

type RoleAssetsPageProps = {
  activeRole: RoleRecord | null;
  bridgeReady: boolean;
  savingSelection: boolean;
  roleForm: RoleFormState;
  selectedAvatarAsset: string;
  selectedChatBackground: string;
  onBackToDetail: () => void;
  onPickAssets: (categoryId: string) => void;
  onRemoveAsset: (path: string) => void;
  /** Re-reads the open role after a plugin panel changed data the host stores on it. */
  onPluginRoleDataChanged: () => void;
  onSelectAvatarAsset: (path: string) => void;
  onSelectChatBackground: (path: string) => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  onUpdateAssetOrganization: (
    categories: RoleAssetCategory[],
    bindings: Record<string, string>,
    removedIllustrations?: string[],
  ) => Promise<boolean>;
  onSaveSelections: (nextSelection?: { avatarAsset?: string; chatBackground?: string; moodIllustrationBindings?: Record<string, string> }) => void;
};

/**
 * The role's look: the asset library on the left, and on the right a preview
 * of the clicked image with what to do with it — set it as the avatar or the
 * chat background, bind it to a mood, or delete it.
 */
export function RoleAssetsPage({
  activeRole,
  bridgeReady,
  savingSelection,
  roleForm,
  selectedAvatarAsset,
  selectedChatBackground,
  onBackToDetail,
  onPickAssets,
  onRemoveAsset,
  onPluginRoleDataChanged,
  onSelectAvatarAsset,
  onSelectChatBackground,
  onUpdateRoleForm,
  onUpdateAssetOrganization,
  onSaveSelections,
}: RoleAssetsPageProps) {
  const roleAssetsPanels = useRoleAssetsPanels();
  const [mode, setMode] = useState<RoleAssetMode>("avatar");
  const [focusedAssetPath, setFocusedAssetPath] = useState("");
  const [pendingRemoveAssetPath, setPendingRemoveAssetPath] = useState("");
  const locked = !bridgeReady || savingSelection;
  const preview = resolveRoleAssetPreview({ mode, role: activeRole, focusedPath: focusedAssetPath, selectedAvatarAsset, selectedChatBackground });
  const current = currentRoleAsset(mode, activeRole, selectedAvatarAsset, selectedChatBackground);
  const pendingRemoveIndex = activeRole?.illustrations.indexOf(pendingRemoveAssetPath) ?? -1;
  const pendingRemoveAbsPath = pendingRemoveIndex >= 0 ? (activeRole?.illustrations_abs[pendingRemoveIndex] ?? "") : "";

  function setModeAsset(nextPath: string): void {
    if (mode === "avatar") {
      onSelectAvatarAsset(nextPath);
      onSaveSelections({ avatarAsset: nextPath });
    } else if (mode === "chat-background") {
      onSelectChatBackground(nextPath);
      onSaveSelections({ chatBackground: nextPath });
    }
  }

  function saveMoodBinding(nextMood: string): void {
    if (!preview?.inLibrary) return;
    const nextBindings = applyMoodToIllustration(roleForm.moodIllustrationBindings, preview.relPath, nextMood.trim());
    onUpdateRoleForm((currentForm) => ({ ...currentForm, moodIllustrationBindings: nextBindings }));
    onSaveSelections({ moodIllustrationBindings: nextBindings });
  }

  return (
    <section className="role-assets-page scrollbar-stable h-full overflow-y-auto bg-gradient-app bg-fixed" data-testid="role-assets-page">
      <div className="mx-auto grid w-full max-w-[1280px] gap-5 px-8 pb-10 pt-6">
        <div className="flex items-center gap-3">
          <button className={cx(iconButtonClass, "shadow-soft")} type="button" aria-label="返回角色详情" title="返回角色详情" onClick={onBackToDetail}>
            <BackIcon className="h-5 w-5 fill-current" />
          </button>
          <h1 className="m-0 truncate font-display text-headline text-ink">{activeRole?.name ?? ""}</h1>
        </div>
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="grid content-start gap-6">
            <RoleAssetCategoryGroups
              key={activeRole?.id ?? ""}
              role={activeRole}
              bridgeReady={bridgeReady}
              saving={savingSelection}
              focusedAssetPath={focusedAssetPath}
              onPickAssets={onPickAssets}
              onFocusAsset={setFocusedAssetPath}
              onUpdateOrganization={onUpdateAssetOrganization}
            />
            {/* Plugin-owned panels (#181-D) contribute through `role.assets`, e.g. the desktop pet packages. */}
            {roleAssetsPanels.map((panel) => (
              // Keyed by role as well as by plugin: switching roles must remount so the previous role's data never shows under the new one.
              <panel.Component
                key={`${panel.id}:${activeRole?.id ?? ""}`}
                roleId={activeRole?.id ?? ""}
                disabled={locked}
                onRoleDataChanged={onPluginRoleDataChanged}
              />
            ))}
          </div>
          <RoleAssetPreviewPane
            mode={mode}
            preview={preview}
            current={current}
            previewMood={getMoodForIllustration(preview?.inLibrary ? preview.relPath : "", roleForm.moodIllustrationBindings)}
            locked={locked}
            onModeChange={setMode}
            onApply={setModeAsset}
            onClearCurrent={() => setModeAsset("")}
            onDelete={setPendingRemoveAssetPath}
            onSaveMoodBinding={saveMoodBinding}
          />
        </div>
      </div>
      <ConfirmDialog
        open={pendingRemoveAbsPath !== ""}
        title="删除素材"
        persona={confirmPersonaLines.deleteAsset}
        description="删除后这张图片会从角色素材库中移除，无法恢复。"
        confirmLabel="删除"
        onClose={() => setPendingRemoveAssetPath("")}
        onConfirm={() => {
          onRemoveAsset(pendingRemoveAssetPath);
          if (focusedAssetPath === pendingRemoveAssetPath) setFocusedAssetPath("");
          setPendingRemoveAssetPath("");
        }}
      >
        {pendingRemoveAbsPath ? (
          <img className="h-24 w-24 rounded-md border border-line-soft object-cover" src={toFileUrl(pendingRemoveAbsPath)} alt="待删除的素材" />
        ) : null}
      </ConfirmDialog>
    </section>
  );
}
