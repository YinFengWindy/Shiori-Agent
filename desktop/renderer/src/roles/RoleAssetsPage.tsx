import { toFileUrl } from "../shared/format";
import { cardClass, cx, ghostButtonClass, panelTitleClass, primaryButtonClass } from "../shared/styles";
import type { RoleRecord } from "../shared/types";

type RoleAssetsPageProps = {
  activeRole: RoleRecord | null;
  bridgeReady: boolean;
  savingSelection: boolean;
  selectedAvatarAsset: string;
  selectedFeaturedImage: string;
  onBackToDetail: () => void;
  onPickAssets: () => void;
  onSelectAvatarAsset: (path: string) => void;
  onSelectFeaturedImage: (path: string) => void;
  onSaveSelections: () => void;
};

export function RoleAssetsPage({
  activeRole,
  bridgeReady,
  savingSelection,
  selectedAvatarAsset,
  selectedFeaturedImage,
  onBackToDetail,
  onPickAssets,
  onSelectAvatarAsset,
  onSelectFeaturedImage,
  onSaveSelections,
}: RoleAssetsPageProps) {
  const assetPairs = (activeRole?.illustrations ?? []).map((relPath, index) => ({
    relPath,
    absPath: activeRole?.illustrations_abs[index] ?? "",
  }));

  return (
    <section
      className="role-assets-page scrollbar-soft scrollbar-soft-accent h-full overflow-y-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(248,249,252,0.98)_100%)]"
      data-testid="role-assets-page"
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1120px] flex-col gap-5 px-8 pb-10 pt-10">
        <div className={cx(cardClass, "border-[#D9E0E8] bg-white/92 p-6 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")}>
          <div className="flex items-center justify-between gap-4">
            <div>
              <button
                className={cx("ghost-btn mb-3 px-3 py-2 text-sm", ghostButtonClass)}
                type="button"
                onClick={onBackToDetail}
              >
                返回角色详情
              </button>
              <div className={panelTitleClass}>素材库</div>
              <div className="mt-2 text-sm text-[#7A8593]">上传图片到当前角色素材库，再选择其作为头像或顶栏立绘。</div>
            </div>
            <button
              data-testid="pick-role-assets-button"
              className={cx("primary-btn text-sm", primaryButtonClass)}
              type="button"
              disabled={!bridgeReady}
              onClick={onPickAssets}
            >
              上传素材
            </button>
          </div>
        </div>
        <div className={cx(cardClass, "border-[#D9E0E8] bg-white/92 p-6 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")}>
          <div className="mb-4 grid gap-2 md:grid-cols-2">
            <div className="rounded-[18px] border border-[#E4EAF0] bg-[#F8FBFD] px-4 py-3 text-sm text-[#596776]">
              当前头像：{selectedAvatarAsset || "未设置"}
            </div>
            <div className="rounded-[18px] border border-[#E4EAF0] bg-[#F8FBFD] px-4 py-3 text-sm text-[#596776]">
              当前顶栏立绘：{selectedFeaturedImage || "未设置"}
            </div>
          </div>
          {assetPairs.length ? (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4">
              {assetPairs.map(({ relPath, absPath }, index) => {
                const isAvatar = relPath === selectedAvatarAsset;
                const isFeatured = relPath === selectedFeaturedImage;
                return (
                  <article
                    key={relPath}
                    data-testid={`role-asset-card-${index}`}
                    className={cx(cardClass, "overflow-hidden border-[#D9E0E8] bg-[#FCFDFE] p-3")}
                  >
                    <img className="h-[180px] w-full rounded-[18px] object-cover" src={toFileUrl(absPath)} alt="role asset" />
                    <div className="mt-3 truncate text-xs text-[#5D6876]">{relPath}</div>
                    <div className="mt-3 flex gap-2">
                      <button
                        data-testid={`select-avatar-${index}`}
                        className={cx(
                          "ghost-btn flex-1 px-3 py-2 text-sm",
                          isAvatar ? primaryButtonClass : ghostButtonClass,
                        )}
                        type="button"
                        disabled={!bridgeReady}
                        onClick={() => onSelectAvatarAsset(relPath)}
                      >
                        {isAvatar ? "当前头像" : "设为头像"}
                      </button>
                      <button
                        data-testid={`select-featured-${index}`}
                        className={cx(
                          "ghost-btn flex-1 px-3 py-2 text-sm",
                          isFeatured ? primaryButtonClass : ghostButtonClass,
                        )}
                        type="button"
                        disabled={!bridgeReady}
                        onClick={() => onSelectFeaturedImage(relPath)}
                      >
                        {isFeatured ? "当前立绘" : "设为立绘"}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="grid min-h-[240px] place-items-center rounded-[22px] border border-dashed border-[#D9E0E8] bg-[#F7FAFD] text-sm text-[#74808D]">
              暂无素材，先上传一些图片。
            </div>
          )}
          <div className="mt-6 flex justify-end">
            <button
              data-testid="save-role-assets-button"
              className={cx("primary-btn text-sm", primaryButtonClass)}
              type="button"
              disabled={!bridgeReady || savingSelection}
              onClick={onSaveSelections}
            >
              {savingSelection ? "保存中..." : "应用素材选择"}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
