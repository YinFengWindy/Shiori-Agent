import { useState } from "react";
import { toFileUrl } from "../shared/format";
import { CloseIcon, UploadIcon } from "../shared/icons";
import { cx } from "../shared/styles";
import type { RoleAssetCategory, RoleFormState, RoleRecord } from "../shared/types";
import { getNextRoleAssetSelection, getSelectedRoleAssetPath } from "./roleAssetSelection";
import { applyMoodToIllustration, getMoodForIllustration } from "./roleMoodBindingSelection";
import { RoleMoodBindingsPanel } from "./RoleMoodBindingsPanel";
import { RoleAssetCategoryGroups } from "./RoleAssetCategoryGroups";
import { useRoleAssetsPanels } from "../plugins/useRoleAssetsPanels";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";

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
  const assetPairs = (activeRole?.illustrations ?? []).map((relPath, index) => ({
    relPath,
    absPath: activeRole?.illustrations_abs[index] ?? "",
  }));
  const [selectionMode, setSelectionMode] = useState<"avatar" | "chat-background" | "mood-binding">("avatar");
  const [selectedMoodAsset, setSelectedMoodAsset] = useState("");
  // Removing an asset deletes its file, so both delete buttons on this page
  // (the preview strip and the category groups) go through one confirmation.
  const [pendingRemoveAssetPath, setPendingRemoveAssetPath] = useState("");
  const pendingRemoveAsset = assetPairs.find((item) => item.relPath === pendingRemoveAssetPath) ?? null;
  const selectedAssetPath = getSelectedRoleAssetPath(
    selectionMode === "mood-binding" ? "chat-background" : selectionMode,
    selectedAvatarAsset,
    selectedChatBackground,
  );
  const selectedAsset = assetPairs.find((item) => item.relPath === selectedAssetPath) ?? null;
  const selectedMoodAssetPath = selectionMode === "mood-binding" ? selectedMoodAsset : "";
  const selectedMoodAssetPair = assetPairs.find((item) => item.relPath === selectedMoodAssetPath) ?? null;
  const selectedMood = getMoodForIllustration(selectedMoodAssetPath, roleForm.moodIllustrationBindings);

  function switchSelectionMode(nextMode: "avatar" | "chat-background" | "mood-binding"): void {
    if (nextMode === "mood-binding" && !selectedMoodAsset && selectedAssetPath) {
      setSelectedMoodAsset(selectedAssetPath);
    }
    setSelectionMode(nextMode);
  }

  function saveSingleSelection(mode: "avatar" | "chat-background", nextPath: string): void {
    if (mode === "avatar") {
      onSelectAvatarAsset(nextPath);
      onSaveSelections({ avatarAsset: nextPath });
      return;
    }
    onSelectChatBackground(nextPath);
    onSaveSelections({ chatBackground: nextPath });
  }

  async function applyAsset(relPath: string): Promise<void> {
    if (selectionMode === "avatar") {
      const nextPath = getNextRoleAssetSelection(selectedAssetPath, relPath);
      saveSingleSelection("avatar", nextPath);
    } else if (selectionMode === "chat-background") {
      const nextPath = getNextRoleAssetSelection(selectedAssetPath, relPath);
      saveSingleSelection("chat-background", nextPath);
    } else {
      setSelectedMoodAsset((current) => current === relPath ? "" : relPath);
    }
  }

  function saveMoodBinding(nextMood: string): void {
    if (!selectedMoodAssetPath) return;
    const normalizedMood = nextMood.trim();
    const nextBindings = applyMoodToIllustration(roleForm.moodIllustrationBindings, selectedMoodAssetPath, normalizedMood);
    onUpdateRoleForm((current) => ({
      ...current,
      moodIllustrationBindings: nextBindings,
    }));
    onSaveSelections({ moodIllustrationBindings: nextBindings });
  }

  return (
    <section
      className="role-assets-page scrollbar-soft scrollbar-soft-accent h-full overflow-y-auto bg-white"
      data-testid="role-assets-page"
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1280px] flex-col gap-5 px-8 pb-10 pt-6">
        <div className="grid min-h-[680px] grid-cols-[428px_minmax(0,1fr)] overflow-hidden rounded-lg bg-white/92 shadow-pop">
          <div className="flex min-h-0 flex-col bg-surface-soft p-4">
            <div className="hidden mt-5 grid grid-cols-4 content-start gap-2.5">
              {assetPairs.map(({ relPath, absPath }, index) => {
                const isSelected = selectionMode === "mood-binding"
                  ? selectedMoodAssetPath === relPath
                  : (selectedAsset?.relPath ?? "") === relPath;
                return (
                  <div
                    key={relPath}
                    className="relative h-[90px] w-[90px]"
                  >
                    <button
                      data-testid={`role-asset-card-${index}`}
                      className={cx(
                        "h-[90px] w-[90px] overflow-hidden rounded-lg border p-0 text-left transition",
                        isSelected ? "border-accent shadow-soft" : "border-line-soft bg-white hover:border-line-strong",
                      )}
                      type="button"
                      disabled={!bridgeReady}
                      onClick={() => void applyAsset(relPath)}
                    >
                      <img className="h-full w-full object-cover" src={toFileUrl(absPath)} alt="role asset" />
                    </button>
                    <button
                      className="absolute right-1.5 top-1.5 grid h-6 w-6 place-items-center rounded-full border border-line-soft bg-white/92 text-ink-secondary shadow-soft transition hover:border-line-strong hover:bg-white hover:text-ink"
                      type="button"
                      aria-label="删除素材"
                      disabled={!bridgeReady || savingSelection}
                      onClick={(event) => {
                        event.stopPropagation();
                        setPendingRemoveAssetPath(relPath);
                      }}
                    >
                      <svg viewBox="0 0 20 20" className="h-3.5 w-3.5 fill-current" aria-hidden="true">
                        <path d="M7.5 2.5a1 1 0 0 0-.92.61L6.38 3.5H4a.75.75 0 0 0 0 1.5h.54l.64 9.04A2 2 0 0 0 7.18 16h5.64a2 2 0 0 0 1.99-1.96L15.46 5H16a.75.75 0 0 0 0-1.5h-2.38l-.2-.39a1 1 0 0 0-.92-.61h-5Zm.42 3.5a.75.75 0 0 1 .75.75v5.5a.75.75 0 0 1-1.5 0v-5.5A.75.75 0 0 1 7.92 6Zm4.16 0a.75.75 0 0 1 .75.75v5.5a.75.75 0 0 1-1.5 0v-5.5a.75.75 0 0 1 .75-.75Z" />
                      </svg>
                    </button>
                  </div>
                );
              })}
              <button
                data-testid="pick-role-assets-button"
                className="grid h-[90px] w-[90px] place-items-center overflow-hidden rounded-lg border border-line-soft bg-white text-ink transition hover:border-line-strong hover:bg-surface-hover disabled:cursor-default disabled:border-black/6 disabled:bg-white/60 disabled:text-ink-faint"
                type="button"
                disabled={!bridgeReady}
                onClick={() => onPickAssets("default")}
                aria-label="上传素材"
              >
                <UploadIcon className="h-8 w-8 fill-current" />
              </button>
            </div>
            <div className="mt-5 min-h-0 flex-1">
              <RoleAssetCategoryGroups
                role={activeRole}
                bridgeReady={bridgeReady}
                saving={savingSelection}
                selectedAssetPath={selectionMode === "mood-binding" ? selectedMoodAssetPath : selectedAsset?.relPath ?? ""}
                onBackToDetail={onBackToDetail}
                onPickAssets={onPickAssets}
                onRemoveAsset={setPendingRemoveAssetPath}
                onSelectAsset={(relPath) => void applyAsset(relPath)}
                onUpdateOrganization={onUpdateAssetOrganization}
              />
            </div>
            {/*
              * Plugin-owned panels (#181-D). The desktop pet's package manager
              * used to be rendered here by name, which meant this page — and
              * `RoleRecord`, and four props above — had to know what a pet
              * package is. It now contributes itself through `role.assets`.
              */}
            {roleAssetsPanels.map((panel) => (
              <panel.Component
                // Keyed by role as well as by plugin: switching roles must
                // remount rather than hand the same component a new `roleId`,
                // which would leave the previous role's data (and any in-flight
                // request for it) on screen under the new role's heading.
                key={`${panel.id}:${activeRole?.id ?? ""}`}
                roleId={activeRole?.id ?? ""}
                disabled={!bridgeReady || savingSelection}
                onRoleDataChanged={onPluginRoleDataChanged}
              />
            ))}
          </div>
          <div className="grid min-h-0 grid-rows-[minmax(0,1fr)] bg-white p-6">
            <div className="flex min-h-0 flex-col">
              <div className="flex h-full min-h-[420px] flex-col rounded-xl border border-line-soft bg-surface-soft p-5">
                <div className="mb-4 flex items-center justify-between gap-4">
                  <div className="text-sm font-medium text-ink">
                    {selectionMode === "avatar" ? "头像效果" : selectionMode === "chat-background" ? "立绘效果" : "差分效果"}
                  </div>
                  <div className="inline-flex rounded-full border border-line-soft bg-surface-soft p-1">
                    <button
                      data-testid="selection-mode-avatar"
                      className={cx(
                        "rounded-full px-4 py-2 text-sm transition",
                        selectionMode === "avatar" ? "bg-gradient-accent text-ink shadow-soft" : "text-ink-secondary hover:text-ink",
                      )}
                      type="button"
                      onClick={() => switchSelectionMode("avatar")}
                    >
                      头像
                    </button>
                    <button
                      data-testid="selection-mode-featured"
                      className={cx(
                        "rounded-full px-4 py-2 text-sm transition",
                        selectionMode === "chat-background" ? "bg-gradient-accent text-ink shadow-soft" : "text-ink-secondary hover:text-ink",
                      )}
                      type="button"
                      onClick={() => switchSelectionMode("chat-background")}
                    >
                      立绘
                    </button>
                    <button
                      data-testid="selection-mode-mood-binding"
                      className={cx(
                        "rounded-full px-4 py-2 text-sm transition",
                        selectionMode === "mood-binding" ? "bg-gradient-accent text-ink shadow-soft" : "text-ink-secondary hover:text-ink",
                      )}
                      type="button"
                      onClick={() => switchSelectionMode("mood-binding")}
                    >
                      差分
                    </button>
                  </div>
                </div>
                {selectionMode === "mood-binding" ? (
                  <div className="flex min-h-0 flex-1 flex-col">
                    <RoleMoodBindingsPanel
                      selectedAssetPath={selectedMoodAssetPath}
                      selectedAssetAbsPath={selectedMoodAssetPair?.absPath ? toFileUrl(selectedMoodAssetPair.absPath) : ""}
                      selectedMood={selectedMood}
                      onSaveMoodBinding={saveMoodBinding}
                      onClearSelectedAsset={() => setSelectedMoodAsset("")}
                    />
                  </div>
                ) : selectedAsset ? (
                  selectionMode === "avatar" ? (
                    <div className="relative grid min-h-[360px] flex-1 place-items-center rounded-xl bg-white p-8">
                      <button
                        className="absolute right-4 top-4 grid h-8 w-8 place-items-center rounded-md border border-line-soft bg-white/92 text-ink-secondary transition hover:border-line-strong hover:bg-white hover:text-ink focus:outline-none"
                        type="button"
                        onClick={() => saveSingleSelection("avatar", "")}
                        aria-label="取消选中头像"
                      >
                        <CloseIcon className="h-4 w-4 stroke-current" />
                      </button>
                      <img className="h-[140px] w-[140px] rounded-xl object-cover shadow-soft" src={toFileUrl(selectedAsset.absPath)} alt="avatar preview" />
                    </div>
                  ) : (
                    <div className="relative flex min-h-[360px] flex-1 items-center justify-center overflow-hidden rounded-xl bg-white p-6">
                      <button
                        className="absolute right-4 top-4 grid h-8 w-8 place-items-center rounded-md border border-line-soft bg-white/92 text-ink-secondary transition hover:border-line-strong hover:bg-white hover:text-ink focus:outline-none"
                        type="button"
                        onClick={() => saveSingleSelection("chat-background", "")}
                        aria-label="取消选中立绘"
                      >
                        <CloseIcon className="h-4 w-4 stroke-current" />
                      </button>
                      <img
                        className="max-h-full w-full object-contain"
                        src={toFileUrl(selectedAsset.absPath)}
                        alt="featured preview"
                      />
                    </div>
                  )
                ) : (
                  <div className="grid min-h-[360px] flex-1 place-items-center rounded-xl bg-surface-soft text-sm text-ink-muted">
                    {selectionMode === "avatar" ? "当前未设置头像" : "当前未设置立绘"}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
      <ConfirmDialog
        open={pendingRemoveAsset !== null}
        title="删除素材"
        description="删除后这张图片会从角色素材库中移除，无法恢复。"
        confirmLabel="删除"
        onClose={() => setPendingRemoveAssetPath("")}
        onConfirm={() => {
          if (pendingRemoveAsset) onRemoveAsset(pendingRemoveAsset.relPath);
          setPendingRemoveAssetPath("");
        }}
      >
        {pendingRemoveAsset ? (
          <img className="h-24 w-24 rounded-md border border-line-soft object-cover" src={toFileUrl(pendingRemoveAsset.absPath)} alt="待删除的素材" />
        ) : null}
      </ConfirmDialog>
    </section>
  );
}
