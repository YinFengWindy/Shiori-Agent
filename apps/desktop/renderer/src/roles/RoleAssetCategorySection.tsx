import { CaretRight, PaperPlaneTilt, Trash, UploadSimple } from "@phosphor-icons/react";
import { toFileUrl } from "../shared/format";
import { compactPressableClass, cx } from "../shared/styles";
import type { RoleAssetCategory } from "../shared/types";
import type { RoleAssetPair } from "./roleAssetCategories";

type RoleAssetCategorySectionProps = {
  category: RoleAssetCategory;
  assets: RoleAssetPair[];
  expanded: boolean;
  /** An asset is being dragged over this category. */
  dropping: boolean;
  /** The library image the preview pane shows; it gets the selection ring. */
  focusedAssetPath: string;
  /** Actions that change the organization are off while the bridge is down or a save runs. */
  locked: boolean;
  canDelete: boolean;
  onToggle: () => void;
  onRename: (name: string) => void;
  onToggleRoleSend: () => void;
  onDelete: () => void;
  onPickAssets: () => void;
  onFocusAsset: (relPath: string) => void;
  onDragAsset: (relPath: string) => void;
  onDragOver: () => void;
  onDragLeave: () => void;
  onDrop: () => void;
};

const categoryIconButtonBaseClass = cx(compactPressableClass, "grid h-8 w-8 shrink-0 place-items-center rounded-md disabled:cursor-default disabled:opacity-40");
const categoryIconButtonClass = cx(categoryIconButtonBaseClass, "text-ink-muted hover:bg-surface-hover hover:text-ink");
const categoryIconButtonOnClass = cx(categoryIconButtonBaseClass, "bg-accent-soft text-accent-text");

/**
 * One category of the role's asset library: a flat header row (fold, rename,
 * role-send switch, delete) over its thumbnail grid. Clicking a thumbnail
 * only shows it in the preview pane; what to do with it (set, bind, delete)
 * is chosen there, so nothing sits on top of the images.
 */
export function RoleAssetCategorySection({
  category,
  assets,
  expanded,
  dropping,
  focusedAssetPath,
  locked,
  canDelete,
  onToggle,
  onRename,
  onToggleRoleSend,
  onDelete,
  onPickAssets,
  onFocusAsset,
  onDragAsset,
  onDragOver,
  onDragLeave,
  onDrop,
}: RoleAssetCategorySectionProps) {
  return (
    <section
      className={cx("rounded-lg border p-2 transition-colors", dropping ? "border-lavender bg-lavender-soft" : "border-transparent")}
      onDragOver={(event) => {
        event.preventDefault();
        onDragOver();
      }}
      onDragLeave={onDragLeave}
      onDrop={(event) => {
        event.preventDefault();
        onDrop();
      }}
    >
      <div className="flex min-h-10 items-center gap-1.5">
        <button className={categoryIconButtonClass} type="button" aria-label={expanded ? `收起${category.name}` : `展开${category.name}`} onClick={onToggle}>
          <CaretRight className={cx("h-4 w-4 transition-transform duration-quick", expanded && "rotate-90")} weight="bold" aria-hidden="true" />
        </button>
        <input
          className="h-8 min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1.5 text-body font-medium text-ink transition hover:bg-surface-hover focus:bg-surface"
          defaultValue={category.name}
          aria-label={`${category.name}分类名称`}
          onBlur={(event) => onRename(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
        />
        <span className="min-w-6 text-center text-caption tabular-nums text-ink-muted">{assets.length}</span>
        <button
          className={category.allow_role_send ? categoryIconButtonOnClass : categoryIconButtonClass}
          type="button"
          aria-pressed={category.allow_role_send}
          aria-label={category.allow_role_send ? "禁止角色发送此分类" : "允许角色发送此分类"}
          title={category.allow_role_send ? "角色可发送" : "角色不可发送"}
          disabled={locked}
          onClick={onToggleRoleSend}
        >
          <PaperPlaneTilt className="h-4 w-4" aria-hidden="true" />
        </button>
        <button className={categoryIconButtonClass} type="button" aria-label={`删除分类${category.name}`} disabled={locked || !canDelete} onClick={onDelete}>
          <Trash className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      {expanded ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(84px,1fr))] gap-2.5 px-1 pb-1 pt-2">
          {assets.map(({ relPath, absPath }) => (
            <button
              className={cx(
                compactPressableClass,
                "aspect-square overflow-hidden rounded-md border-2 bg-surface-soft p-0",
                focusedAssetPath === relPath ? "border-accent shadow-soft" : "border-transparent hover:border-line-strong",
              )}
              key={relPath}
              type="button"
              draggable
              aria-pressed={focusedAssetPath === relPath}
              aria-label="查看素材"
              onDragStart={() => onDragAsset(relPath)}
              onDragEnd={() => onDragAsset("")}
              onClick={() => onFocusAsset(relPath)}
            >
              <img className="h-full w-full object-cover" src={toFileUrl(absPath)} alt="" />
            </button>
          ))}
          <button
            className={cx(compactPressableClass, "grid aspect-square place-items-center rounded-md border border-dashed border-line bg-surface-soft text-ink-muted hover:border-line-strong hover:bg-surface-hover hover:text-ink disabled:cursor-default disabled:opacity-50")}
            type="button"
            aria-label={`上传到${category.name}`}
            title={`上传到${category.name}`}
            disabled={locked}
            onClick={onPickAssets}
          >
            <UploadSimple className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </section>
  );
}
