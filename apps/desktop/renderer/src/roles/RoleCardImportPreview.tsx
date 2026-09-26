import { useEffect } from "react";

import { CloseIcon, DocumentIcon } from "../shared/icons";
import { compactButtonSizeClass, compactPressableClass, cx, ghostButtonSurfaceClass, primaryButtonSurfaceClass } from "../shared/styles";
import type { RoleCardImportPreview } from "../shared/types";
import { RoleCardImportAssets } from "./RoleCardImportAssets";
import { hasUnselectedEmotions } from "./roleCardImportSelectors";

type RoleCardImportPreviewDialogProps = {
  open: boolean;
  preview: RoleCardImportPreview;
  sourceUrl: string;
  onClose: () => void;
  onCancel: () => void;
  selections: Record<string, string>;
  onSelectEmotion: (name: string, assetId: string) => void;
};

type PreviewSectionProps = {
  title: string;
  children: React.ReactNode;
};

/** Flat titled section separated by a hairline instead of a bordered card. */
function PreviewSection({ title, children }: PreviewSectionProps) {
  return (
    <section className="grid gap-3">
      <header className="flex items-center gap-3">
        <h4 className="m-0 shrink-0 text-sm font-semibold text-ink-secondary">{title}</h4>
        <div className="h-px flex-1 bg-line-soft" />
      </header>
      {children}
    </section>
  );
}

/** One labeled prose block inside the character section. */
function PreviewField({ label, value }: { label: string; value: string }) {
  if (!value.trim()) return null;
  return (
    <div className="grid gap-1">
      <p className="m-0 text-xs font-medium text-ink-faint">{label}</p>
      <p className="m-0 whitespace-pre-wrap text-xs leading-5 text-ink-secondary">{value}</p>
    </div>
  );
}

/** Displays a scrollable staged-card inspection dialog before creation. */
export function RoleCardImportPreviewDialog({
  open,
  preview,
  sourceUrl,
  onClose,
  onCancel,
  selections,
  onSelectEmotion,
}: RoleCardImportPreviewDialogProps) {
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [onClose, open]);

  if (!open) return null;

  const character = preview.profile?.character;
  const assets = (preview.assets ?? []).filter((asset) => asset.size !== undefined);
  const hasCharacterContent = Boolean(
    character?.profile || preview.description || character?.personality || character?.behavior_rules || character?.response_constraints,
  );

  return (
    <div className="role-card-import-dialog fixed inset-0 z-40 flex items-center justify-center px-4 py-6">
      <button className="absolute inset-0 border-0 bg-[rgba(15,23,42,0.34)] p-0 backdrop-blur-[6px]" type="button" aria-label="关闭角色卡预览" onClick={onClose} />
      <section className="relative z-[1] grid max-h-[min(88vh,960px)] w-full max-w-[720px] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-xl bg-surface shadow-pop" role="dialog" aria-modal="true" aria-label="角色卡导入预览" data-testid="role-card-import-preview">
        <header className="flex items-start justify-between gap-4 border-b border-line-soft px-6 py-5">
          <div className="flex min-w-0 items-center gap-3.5">
            {sourceUrl ? (
              <img className="h-16 w-16 shrink-0 rounded-full object-cover shadow-soft" src={sourceUrl} alt={`${preview.name ?? "角色卡"}预览`} />
            ) : (
              <div className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-surface-soft text-ink-muted">
                <DocumentIcon className="h-6 w-6 stroke-current" />
              </div>
            )}
            <div className="min-w-0">
              <h3 className="truncate text-base font-semibold text-ink">{preview.name || "未命名角色"}</h3>
              <p className="mt-1 text-xs text-ink-faint">{[preview.provenance?.format, preview.provenance?.card_version].filter(Boolean).join(" · ") || "角色卡"}</p>
            </div>
          </div>
          <button className={cx(compactPressableClass, "grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink-secondary")} type="button" onClick={onClose} aria-label="关闭角色卡预览" title="关闭角色卡预览">
            <CloseIcon className="h-4 w-4 stroke-current" />
          </button>
        </header>

        <div className="role-card-import-dialog-content scrollbar-stable min-h-0 overflow-y-auto px-6 py-5">
          <div className="grid gap-6">
            <PreviewSection title="角色设定">
              {hasCharacterContent ? (
                <div className="grid gap-3">
                  <PreviewField label="设定" value={character?.profile || preview.description || ""} />
                  <PreviewField label="性格" value={character?.personality ?? ""} />
                  <PreviewField label="规则" value={character?.behavior_rules ?? ""} />
                  <PreviewField label="回复约束" value={character?.response_constraints ?? ""} />
                </div>
              ) : <p className="m-0 text-xs text-ink-faint">无</p>}
            </PreviewSection>

            {(preview.report?.discarded_fields ?? []).length > 0 ? (
              <PreviewSection title="未导入内容">
                <p className="m-0 text-xs leading-5 text-ink-secondary">{preview.report?.discarded_fields?.join("、")}</p>
              </PreviewSection>
            ) : null}
            <PreviewSection title={`素材 · ${assets.length}`}>
              {assets.length ? (
                <RoleCardImportAssets assets={assets} selections={selections} onSelectEmotion={onSelectEmotion} />
              ) : <p className="m-0 text-xs text-ink-faint">无</p>}
            </PreviewSection>
          </div>
        </div>

        <footer className="flex justify-end gap-2 border-t border-line-soft px-6 py-4">
          <button className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} type="button" onClick={onCancel}>取消导入</button>
          <button className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)} type="button" disabled={hasUnselectedEmotions(assets, selections)} onClick={onClose}>继续编辑</button>
        </footer>
      </section>
    </div>
  );
}
