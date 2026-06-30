import { useState } from "react";
import { toFileUrl } from "../shared/format";
import { SaveIcon, UploadIcon } from "../shared/icons";
import { cx } from "../shared/styles";
import type { RoleRecord } from "../shared/types";

type RoleAssetsPageProps = {
  activeRole: RoleRecord | null;
  bridgeReady: boolean;
  savingSelection: boolean;
  selectedAssetPath: string;
  selectedAvatarAsset: string;
  selectedFeaturedImage: string;
  onBackToDetail: () => void;
  onPickAssets: () => void;
  onSelectAsset: (path: string) => void;
  onSelectAvatarAsset: (path: string) => void;
  onSelectFeaturedImage: (path: string) => void;
  onSaveSelections: (nextSelection?: { avatarAsset?: string; featuredImage?: string }) => void;
};

export function RoleAssetsPage({
  activeRole,
  bridgeReady,
  savingSelection,
  selectedAssetPath,
  selectedAvatarAsset,
  selectedFeaturedImage,
  onBackToDetail,
  onPickAssets,
  onSelectAsset,
  onSelectAvatarAsset,
  onSelectFeaturedImage,
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
  const selectedAsset = assetPairs.find((item) => item.relPath === selectedAssetPath) ?? assetPairs[0] ?? null;
  const [selectionMode, setSelectionMode] = useState<"avatar" | "featured">("featured");

  async function applyAsset(relPath: string): Promise<void> {
    onSelectAsset(relPath);
    if (selectionMode === "avatar") {
      onSelectAvatarAsset(relPath);
      onSaveSelections({ avatarAsset: relPath });
    } else {
      onSelectFeaturedImage(relPath);
      onSaveSelections({ featuredImage: relPath });
    }
  }

  return (
    <section
      className="role-assets-page scrollbar-soft scrollbar-soft-accent h-full overflow-y-auto bg-white"
      data-testid="role-assets-page"
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1280px] flex-col gap-5 px-8 pb-10 pt-8">
        <div className="grid min-h-[680px] grid-cols-[320px_minmax(0,1fr)] overflow-hidden rounded-[18px] bg-white/92 shadow-[0_18px_48px_rgba(31,41,55,0.08)]">
          <div className="bg-[#FBFCFE] p-5">
            <button
              className="mb-3 grid h-10 w-10 place-items-center rounded-full border border-black/8 bg-white shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 hover:border-black/14 hover:bg-[#F5F7FA] hover:shadow-[0_14px_28px_rgba(15,23,42,0.14)]"
              type="button"
              onClick={onBackToDetail}
              aria-label="返回角色详情"
            >
              {backIcon}
            </button>
            <button
              data-testid="pick-role-assets-button"
              className="grid h-10 w-10 place-items-center rounded-full border border-black/8 bg-white text-[#272536] shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 hover:border-black/14 hover:bg-[#F5F7FA] hover:shadow-[0_14px_28px_rgba(15,23,42,0.14)] disabled:cursor-default disabled:border-black/6 disabled:bg-white/60 disabled:text-[#b8b8b8] disabled:shadow-none"
              type="button"
              disabled={!bridgeReady}
              onClick={onPickAssets}
              aria-label="上传素材"
            >
              <UploadIcon className="h-[18px] w-[18px] fill-current" />
            </button>
            <div className="mt-6 grid content-start gap-3">
              {assetPairs.length ? assetPairs.map(({ relPath, absPath }, index) => {
                const isSelected = (selectedAsset?.relPath ?? "") === relPath;
                return (
                  <button
                    key={relPath}
                    data-testid={`role-asset-card-${index}`}
                    className={cx(
                      "grid gap-2 rounded-[20px] border p-3 text-left transition",
                      isSelected ? "border-[#272536] bg-[#F4F5F8] shadow-[0_8px_24px_rgba(39,37,54,0.12)]" : "border-[#D8DFE7] bg-white hover:border-[#9AA3B2]",
                    )}
                    type="button"
                    onClick={() => void applyAsset(relPath)}
                  >
                    <img className="h-[132px] w-full rounded-[16px] object-cover" src={toFileUrl(absPath)} alt="role asset" />
                  </button>
                );
              }) : (
                <div className="grid min-h-[240px] place-items-center rounded-[22px] bg-[#F7FAFD] text-sm text-[#74808D]">
                  暂无素材
                </div>
              )}
            </div>
          </div>
          <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-white p-6">
            <div className="flex items-start justify-between gap-4">
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
                    selectionMode === "featured" ? "bg-[#272536] text-white shadow-[0_6px_16px_rgba(39,37,54,0.18)]" : "text-[#5B6472] hover:text-[#272536]",
                  )}
                  type="button"
                  onClick={() => setSelectionMode("featured")}
                >
                  立绘
                </button>
              </div>
              {savingSelection ? <div className="flex items-center gap-2 text-sm text-[#5B6472]"><SaveIcon className="h-4 w-4 fill-current" />保存中...</div> : null}
            </div>
            <div className="mt-6 grid min-h-0 gap-5 lg:grid-cols-[minmax(0,1.2fr)_320px]">
              <div className="rounded-[24px] border border-[#E4EAF0] bg-[#FAFBFD] p-5">
                {selectedAsset ? (
                  <img
                    className="h-[380px] w-full rounded-[20px] bg-white object-contain"
                    src={toFileUrl(selectedAsset.absPath)}
                    alt="selected role asset"
                  />
                ) : (
                  <div className="grid h-[380px] place-items-center rounded-[20px] bg-[#F2F5F8] text-sm text-[#74808D]">
                    选择左侧素材以预览
                  </div>
                )}
              </div>
              <div className="grid content-start gap-4">
                <div className="rounded-[22px] border border-[#E4EAF0] bg-[#FAFBFD] p-4">
                  <div className="text-sm font-medium text-[#2A3440]">头像效果</div>
                  <div className="mt-4 grid min-h-[180px] place-items-center rounded-[20px] bg-white">
                    {selectedAsset ? (
                      <img className="h-[116px] w-[116px] rounded-[28px] object-cover shadow-[0_10px_24px_rgba(15,23,42,0.08)]" src={toFileUrl(selectedAsset.absPath)} alt="avatar preview" />
                    ) : (
                      <div className="text-sm text-[#7A8593]">未选择素材</div>
                    )}
                  </div>
                </div>
                <div className="rounded-[22px] border border-[#E4EAF0] bg-[#FAFBFD] p-4">
                  <div className="text-sm font-medium text-[#2A3440]">顶栏立绘效果</div>
                  <div className="mt-4 h-[220px] overflow-hidden rounded-[20px] bg-white">
                    {selectedAsset ? (
                      <div className="h-full w-full bg-cover bg-center bg-no-repeat" style={{ backgroundImage: `url("${toFileUrl(selectedAsset.absPath)}")` }} />
                    ) : (
                      <div className="grid h-full place-items-center text-sm text-[#7A8593]">未选择素材</div>
                    )}
                  </div>
                </div>
                <div className="rounded-[18px] border border-[#E4EAF0] bg-[#F8FBFD] px-4 py-3 text-sm text-[#596776]">
                  当前头像：{selectedAvatarAsset || "未设置"}
                </div>
                <div className="rounded-[18px] border border-[#E4EAF0] bg-[#F8FBFD] px-4 py-3 text-sm text-[#596776]">
                  当前顶栏立绘：{selectedFeaturedImage || "未设置"}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
