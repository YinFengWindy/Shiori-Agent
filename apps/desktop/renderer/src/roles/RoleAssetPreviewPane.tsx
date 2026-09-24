import { Check, ImageSquare, Trash, X } from "@phosphor-icons/react";
import { toFileUrl } from "../shared/format";
import {
  badgeClass,
  cardClass,
  compactButtonSizeClass,
  cx,
  dangerGhostButtonSurfaceClass,
  ghostButtonSurfaceClass,
  primaryButtonSurfaceClass,
} from "../shared/styles";
import type { RoleAssetMode, RoleAssetPreview } from "./roleAssetPreview";
import { roleAssetModes } from "./roleAssetPreview";
import { RoleMoodBindingsPanel } from "./RoleMoodBindingsPanel";

type RoleAssetPreviewPaneProps = {
  mode: RoleAssetMode;
  /** The image shown: the clicked library image, else what the mode has set. */
  preview: RoleAssetPreview | null;
  /** What the mode has set now (avatar / chat background); null for none or for mood bindings. */
  current: RoleAssetPreview | null;
  /** The mood the previewed image is bound to (mood mode). */
  previewMood: string;
  locked: boolean;
  onModeChange: (mode: RoleAssetMode) => void;
  onApply: (relPath: string) => void;
  onClearCurrent: () => void;
  onDelete: (relPath: string) => void;
  onSaveMoodBinding: (mood: string) => void;
};

const copy: Record<Exclude<RoleAssetMode, "mood-binding">, { apply: string; clear: string; current: string; empty: string }> = {
  avatar: { apply: "设为头像", clear: "移除头像", current: "当前头像", empty: "未设置头像" },
  "chat-background": { apply: "设为聊天背景", clear: "清除聊天背景", current: "当前聊天背景", empty: "未设置聊天背景" },
};

const actionClass = compactButtonSizeClass;

/** The assets page's right pane: mode tabs, a preview of one image, and the explicit actions on it. */
export function RoleAssetPreviewPane({
  mode,
  preview,
  current,
  previewMood,
  locked,
  onModeChange,
  onApply,
  onClearCurrent,
  onDelete,
  onSaveMoodBinding,
}: RoleAssetPreviewPaneProps) {
  const modeCopy = mode === "mood-binding" ? null : copy[mode];

  return (
    <aside className="grid content-start gap-4 lg:sticky lg:top-0" data-testid="role-asset-preview">
      <div className="grid grid-cols-3 gap-1 rounded-md bg-surface-soft p-1" role="tablist" aria-label="素材用途">
        {roleAssetModes.map((item) => (
          <button
            key={item.id}
            className={cx(
              "h-8 rounded-md text-body-sm transition-colors duration-quick",
              mode === item.id ? "bg-surface font-medium text-ink shadow-soft" : "text-ink-muted hover:text-ink",
            )}
            data-testid={`selection-mode-${item.id}`}
            type="button"
            role="tab"
            aria-selected={mode === item.id}
            onClick={() => onModeChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className={cx(cardClass, "grid gap-4 p-4")}>
        <div className={cx("relative grid place-items-center overflow-hidden rounded-md bg-gradient-accent-soft", mode === "avatar" ? "h-64" : "aspect-[4/5]")}>
          {preview ? (
            mode === "avatar"
              ? <img className="h-44 w-44 rounded-full border-4 border-white/90 object-cover shadow-panel" src={toFileUrl(preview.absPath)} alt="头像预览" />
              : <img className={cx("h-full w-full", mode === "chat-background" ? "object-cover" : "object-contain")} src={toFileUrl(preview.absPath)} alt="素材预览" />
          ) : (
            <div className="grid justify-items-center gap-2 text-ink-muted">
              <ImageSquare className="h-8 w-8 opacity-60" aria-hidden="true" />
              {modeCopy ? <span className="text-body-sm">{modeCopy.empty}</span> : null}
            </div>
          )}
          {modeCopy && preview?.isCurrent ? (
            <span className={cx(badgeClass, "absolute left-3 top-3 shadow-soft")}>
              <Check className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              {modeCopy.current}
            </span>
          ) : null}
        </div>
        {mode === "mood-binding" ? (
          <RoleMoodBindingsPanel selectedAssetPath={preview?.inLibrary ? preview.relPath : ""} selectedMood={previewMood} onSaveMoodBinding={onSaveMoodBinding} />
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          {modeCopy ? (
            <>
              <button
                className={cx(primaryButtonSurfaceClass, actionClass)}
                type="button"
                data-testid="apply-role-asset"
                disabled={locked || !preview?.inLibrary || preview.isCurrent}
                onClick={() => preview && onApply(preview.relPath)}
              >
                {modeCopy.apply}
              </button>
              {current ? (
                <button className={cx(ghostButtonSurfaceClass, actionClass)} type="button" disabled={locked} onClick={onClearCurrent}>
                  <X className="h-4 w-4" aria-hidden="true" />
                  {modeCopy.clear}
                </button>
              ) : null}
            </>
          ) : null}
          {preview?.inLibrary ? (
            <button className={cx(dangerGhostButtonSurfaceClass, actionClass, "ml-auto")} type="button" aria-label="删除素材" disabled={locked} onClick={() => onDelete(preview.relPath)}>
              <Trash className="h-4 w-4" aria-hidden="true" />
              删除
            </button>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
