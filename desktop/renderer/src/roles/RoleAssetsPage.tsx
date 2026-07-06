import { useState } from "react";
import { toFileUrl } from "../shared/format";
import { UploadIcon } from "../shared/icons";
import { cx } from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { getNextRoleAssetSelection, getSelectedRoleAssetPath } from "./roleAssetSelection";
import { RoleMoodBindingsPanel } from "./RoleMoodBindingsPanel";

type RoleAssetsPageProps = {
  activeRole: RoleRecord | null;
  bridgeReady: boolean;
  savingSelection: boolean;
  roleForm: RoleFormState;
  selectedAvatarAsset: string;
  selectedChatBackground: string;
  onBackToDetail: () => void;
  onPickAssets: () => void;
  onRemoveAsset: (path: string) => void;
  onSelectAvatarAsset: (path: string) => void;
  onSelectChatBackground: (path: string) => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
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
  onSelectAvatarAsset,
  onSelectChatBackground,
  onUpdateRoleForm,
  onSaveSelections,
}: RoleAssetsPageProps) {
  const backIcon = (
    <svg viewBox="0 0 1024 1024" className="h-5 w-5 fill-[#111111]" aria-hidden="true">
      <path d="M631.04 161.941333a42.666667 42.666667 0 0 1 63.061333 57.386667l-2.474666 2.730667-289.962667 292.245333 289.706667 287.402667a42.666667 42.666667 0 0 1 2.730666 57.6l-2.474666 2.752a42.666667 42.666667 0 0 1-57.6 2.709333l-2.752-2.474667-320-317.44a42.666667 42.666667 0 0 1-2.709334-57.6l2.474667-2.752 320-322.56z" />
    </svg>
  );
  const assetPairs = (activeRole?.illustrations ?? []).map((relPath, index) => ({
    relPath,
    absPath: activeRole?.illustrations_abs[index] ?? "",
  }));
  const [selectionMode, setSelectionMode] = useState<"avatar" | "chat-background" | "mood-binding">("avatar");
  const [activeMood, setActiveMood] = useState(roleForm.defaultMood || roleForm.moodCatalog[0] || "");
  const selectedAssetPath = getSelectedRoleAssetPath(
    selectionMode === "mood-binding" ? "chat-background" : selectionMode,
    selectedAvatarAsset,
    selectedChatBackground,
  );
  const selectedAsset = assetPairs.find((item) => item.relPath === selectedAssetPath) ?? null;
  const activeMoodIllustrationPath = activeMood ? (roleForm.moodIllustrationBindings[activeMood] ?? "") : "";
  const activeMoodIllustration = assetPairs.find((item) => item.relPath === activeMoodIllustrationPath) ?? null;

  async function applyAsset(relPath: string): Promise<void> {
    if (selectionMode === "avatar") {
      const nextPath = getNextRoleAssetSelection(selectedAssetPath, relPath);
      onSelectAvatarAsset(nextPath);
      onSaveSelections({ avatarAsset: nextPath });
    } else if (selectionMode === "chat-background") {
      const nextPath = getNextRoleAssetSelection(selectedAssetPath, relPath);
      onSelectChatBackground(nextPath);
      onSaveSelections({ chatBackground: nextPath });
    }
  }

  function bindSelectedAssetToMood(): void {
    if (!activeMood || !selectedAssetPath) return;
    const nextBindings = {
      ...roleForm.moodIllustrationBindings,
      [activeMood]: selectedAssetPath,
    };
    onUpdateRoleForm((current) => ({
      ...current,
      moodIllustrationBindings: nextBindings,
    }));
    onSaveSelections({ moodIllustrationBindings: nextBindings });
  }

  function clearMoodBinding(): void {
    if (!activeMood) return;
    const nextBindings = { ...roleForm.moodIllustrationBindings };
    delete nextBindings[activeMood];
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
        <div className="grid min-h-[680px] grid-cols-[428px_minmax(0,1fr)] overflow-hidden rounded-[18px] bg-white/92 shadow-[0_18px_48px_rgba(31,41,55,0.08)]">
          <div className="bg-[#FBFCFE] p-4">
            <button
              className="mb-2 grid h-10 w-10 place-items-center rounded-full border border-black/8 bg-white shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 hover:border-black/14 hover:bg-[#F5F7FA] hover:shadow-[0_14px_28px_rgba(15,23,42,0.14)]"
              type="button"
              onClick={onBackToDetail}
              aria-label="返回角色详情"
            >
              {backIcon}
            </button>
            <div className="mt-5 grid grid-cols-4 content-start gap-2.5">
              {assetPairs.map(({ relPath, absPath }, index) => {
                const isSelected = (selectedAsset?.relPath ?? "") === relPath;
                return (
                  <div
                    key={relPath}
                    className="relative h-[90px] w-[90px]"
                  >
                    <button
                      data-testid={`role-asset-card-${index}`}
                      className={cx(
                        "h-[90px] w-[90px] overflow-hidden rounded-[18px] border p-0 text-left transition",
                        isSelected ? "border-[#272536] shadow-[0_8px_24px_rgba(39,37,54,0.16)]" : "border-[#D8DFE7] bg-white hover:border-[#9AA3B2]",
                      )}
                      type="button"
                      disabled={!bridgeReady || savingSelection}
                      onClick={() => void applyAsset(relPath)}
                    >
                      <img className="h-full w-full object-cover" src={toFileUrl(absPath)} alt="role asset" />
                    </button>
                    <button
                      className="absolute right-1.5 top-1.5 grid h-6 w-6 place-items-center rounded-full border border-black/10 bg-white/92 text-[#5B6472] shadow-[0_4px_12px_rgba(15,23,42,0.12)] transition hover:border-[#9AA3B2] hover:bg-white hover:text-[#272536]"
                      type="button"
                      aria-label="删除素材"
                      disabled={!bridgeReady || savingSelection}
                      onClick={(event) => {
                        event.stopPropagation();
                        onRemoveAsset(relPath);
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
                className="grid h-[90px] w-[90px] place-items-center overflow-hidden rounded-[18px] border border-[#D8DFE7] bg-white text-[#272536] transition hover:border-[#9AA3B2] hover:bg-[#F5F7FA] disabled:cursor-default disabled:border-black/6 disabled:bg-white/60 disabled:text-[#b8b8b8]"
                type="button"
                disabled={!bridgeReady}
                onClick={onPickAssets}
                aria-label="上传素材"
              >
                <UploadIcon className="h-8 w-8 fill-current" />
              </button>
            </div>
          </div>
          <div className="grid min-h-0 grid-rows-[minmax(0,1fr)] bg-white p-6">
            <div className="flex min-h-0 flex-col">
              <div className="flex h-full min-h-[420px] flex-col rounded-[24px] border border-[#E4EAF0] bg-[#FAFBFD] p-5">
                <div className="mb-4 flex items-center justify-between gap-4">
                  <div className="text-sm font-medium text-[#2A3440]">
                    {selectionMode === "avatar" ? "头像效果" : "立绘效果"}
                  </div>
                  <div className="inline-flex rounded-full border border-[#D8DFE7] bg-[#F6F8FB] p-1">
                    <button
                      data-testid="selection-mode-avatar"
                      className={cx(
                        "rounded-full px-4 py-2 text-sm transition",
                        selectionMode === "avatar" ? "bg-[#272536] text-white shadow-[0_6px_16px_rgba(39,37,54,0.18)]" : "text-[#5B6472] hover:text-[#272536]",
                      )}
                      type="button"
                      onClick={() => setSelectionMode("avatar")}
                    >
                      头像
                    </button>
                    <button
                      data-testid="selection-mode-featured"
                      className={cx(
                        "rounded-full px-4 py-2 text-sm transition",
                        selectionMode === "chat-background" ? "bg-[#272536] text-white shadow-[0_6px_16px_rgba(39,37,54,0.18)]" : "text-[#5B6472] hover:text-[#272536]",
                      )}
                      type="button"
                      onClick={() => setSelectionMode("chat-background")}
                    >
                      默认立绘
                    </button>
                    <button
                      data-testid="selection-mode-mood-binding"
                      className={cx(
                        "rounded-full px-4 py-2 text-sm transition",
                        selectionMode === "mood-binding" ? "bg-[#272536] text-white shadow-[0_6px_16px_rgba(39,37,54,0.18)]" : "text-[#5B6472] hover:text-[#272536]",
                      )}
                      type="button"
                      onClick={() => setSelectionMode("mood-binding")}
                    >
                      心情映射
                    </button>
                  </div>
                </div>
                {selectionMode === "mood-binding" ? (
                  <RoleMoodBindingsPanel
                    moodCatalog={roleForm.moodCatalog}
                    defaultMood={roleForm.defaultMood}
                    activeMood={activeMood}
                    activeMoodIllustrationPath={activeMoodIllustrationPath}
                    activeMoodIllustrationAbsPath={activeMoodIllustration?.absPath ? toFileUrl(activeMoodIllustration.absPath) : ""}
                    selectedAssetPath={selectedAssetPath}
                    onSelectMood={setActiveMood}
                    onBindSelectedAsset={bindSelectedAssetToMood}
                    onClearMoodBinding={clearMoodBinding}
                  />
                ) : selectedAsset ? (
                  selectionMode === "avatar" ? (
                    <div className="grid min-h-[360px] flex-1 place-items-center rounded-[20px] bg-white p-8">
                      <img className="h-[140px] w-[140px] rounded-[32px] object-cover shadow-[0_10px_24px_rgba(15,23,42,0.08)]" src={toFileUrl(selectedAsset.absPath)} alt="avatar preview" />
                    </div>
                  ) : (
                    <div className="flex min-h-[360px] flex-1 items-center justify-center overflow-hidden rounded-[20px] bg-white p-6">
                      <img
                        className="max-h-full w-full object-contain"
                        src={toFileUrl(selectedAsset.absPath)}
                        alt="featured preview"
                      />
                    </div>
                  )
                ) : (
                  <div className="grid min-h-[360px] flex-1 place-items-center rounded-[20px] bg-[#F2F5F8] text-sm text-[#74808D]">
                    {selectionMode === "avatar" ? "当前未设置头像" : "当前未设置立绘"}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
