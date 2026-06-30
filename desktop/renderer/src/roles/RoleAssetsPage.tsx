import { toFileUrl } from "../shared/format";
import { cardClass, cx, ghostButtonClass, panelTitleClass, primaryButtonClass } from "../shared/styles";
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
  onSaveSelections: () => void;
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

  return (
    <section
      className="role-assets-page scrollbar-soft scrollbar-soft-accent h-full overflow-y-auto bg-white"
      data-testid="role-assets-page"
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1280px] flex-col gap-5 px-8 pb-10 pt-10">
        <div className={cx(cardClass, "grid min-h-[680px] grid-cols-[320px_minmax(0,1fr)] overflow-hidden border-[#D9E0E8] bg-white/92 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")}>
          <div className="border-r border-[#E4EAF0] bg-[#FBFCFE] p-5">
            <button
              className="mb-4 grid h-10 w-10 place-items-center rounded-full border border-black/8 bg-white shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 hover:border-black/14 hover:bg-[#F5F7FA] hover:shadow-[0_14px_28px_rgba(15,23,42,0.14)]"
              type="button"
              onClick={onBackToDetail}
              aria-label="返回角色详情"
            >
              {backIcon}
            </button>
            <div className={panelTitleClass}>素材库</div>
            <div className="mt-2 text-sm text-[#7A8593]">左侧上传与选择素材，右侧查看效果并决定用途。</div>
            <button
              data-testid="pick-role-assets-button"
              className={cx("primary-btn mt-5 w-full text-sm", primaryButtonClass)}
              type="button"
              disabled={!bridgeReady}
              onClick={onPickAssets}
            >
              上传素材
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
                      isSelected ? "border-[#7C6BFF] bg-[#F3F1FF] shadow-[0_8px_24px_rgba(124,107,255,0.12)]" : "border-[#E4EAF0] bg-white hover:border-[#D6DEEA]",
                    )}
                    type="button"
                    onClick={() => onSelectAsset(relPath)}
                  >
                    <img className="h-[132px] w-full rounded-[16px] object-cover" src={toFileUrl(absPath)} alt="role asset" />
                    <div className="truncate text-xs text-[#5D6876]">{relPath}</div>
                  </button>
                );
              }) : (
                <div className="grid min-h-[240px] place-items-center rounded-[22px] border border-dashed border-[#D9E0E8] bg-[#F7FAFD] text-sm text-[#74808D]">
                  暂无素材
                </div>
              )}
            </div>
          </div>
          <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-white p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className={panelTitleClass}>素材预览</div>
                <div className="mt-2 text-sm text-[#7A8593]">在右侧查看素材效果，再决定是否设为头像或顶栏立绘。</div>
              </div>
              <div className="flex gap-2">
                <button
                  data-testid="select-avatar-action"
                  className={cx(
                    "ghost-btn px-3 py-2 text-sm",
                    selectedAsset && selectedAvatarAsset === selectedAsset.relPath ? primaryButtonClass : ghostButtonClass,
                  )}
                  type="button"
                  disabled={!bridgeReady || !selectedAsset}
                  onClick={() => selectedAsset && onSelectAvatarAsset(selectedAsset.relPath)}
                >
                  {selectedAsset && selectedAvatarAsset === selectedAsset.relPath ? "当前头像" : "设为头像"}
                </button>
                <button
                  data-testid="select-featured-action"
                  className={cx(
                    "ghost-btn px-3 py-2 text-sm",
                    selectedAsset && selectedFeaturedImage === selectedAsset.relPath ? primaryButtonClass : ghostButtonClass,
                  )}
                  type="button"
                  disabled={!bridgeReady || !selectedAsset}
                  onClick={() => selectedAsset && onSelectFeaturedImage(selectedAsset.relPath)}
                >
                  {selectedAsset && selectedFeaturedImage === selectedAsset.relPath ? "当前立绘" : "设为顶栏立绘"}
                </button>
                <button
                  data-testid="save-role-assets-button"
                  className={cx("primary-btn text-sm", primaryButtonClass)}
                  type="button"
                  disabled={!bridgeReady || savingSelection || !selectedAsset}
                  onClick={onSaveSelections}
                >
                  {savingSelection ? "保存中..." : "应用选择"}
                </button>
              </div>
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
