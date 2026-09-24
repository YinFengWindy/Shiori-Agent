import { ImageSquare, Smiley } from "@phosphor-icons/react";
import { toFileUrl } from "../shared/format";
import { badgeClass, compactButtonSizeClass, cx, ghostButtonSurfaceClass } from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { roleIdentityInputClass } from "./roleEditorStyles";

type RoleDetailHeaderProps = {
  activeRole: RoleRecord | null;
  /** Avatar to show: a just-picked source file or the saved avatar. */
  previewAvatar: string | null;
  /** Portrait drawn faded behind the header's right side; empty for none. */
  portraitUrl: string;
  currentMood: string;
  roleForm: RoleFormState;
  onOpenAssetsPage: () => void;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/**
 * The character header of the role detail page: portrait, avatar, editable
 * name and intro, and the current mood. The name and intro live here rather
 * than in a tab so they are the same on every tab; the page actions sit in the
 * sticky bar below (`RoleDetailToolbar`), clear of the portrait.
 */
export function RoleDetailHeader({
  activeRole,
  previewAvatar,
  portraitUrl,
  currentMood,
  roleForm,
  onOpenAssetsPage,
  onUpdate,
}: RoleDetailHeaderProps) {
  const initial = (roleForm.name || activeRole?.name || "").trim().slice(0, 1).toUpperCase() || "?";

  return (
    <header
      className="relative isolate overflow-hidden rounded-xl border border-white/80 bg-white/70 shadow-soft backdrop-blur-md"
      data-testid="role-detail-header"
      data-has-portrait={portraitUrl ? "true" : "false"}
    >
      {portraitUrl ? (
        <img
          className="pointer-events-none absolute inset-y-0 right-0 -z-10 h-full w-1/2 object-cover object-top [mask-image:linear-gradient(to_left,rgb(0_0_0)_35%,transparent)]"
          src={portraitUrl}
          alt=""
        />
      ) : (
        <div className="pointer-events-none absolute inset-y-0 right-0 -z-10 w-1/2 bg-gradient-accent-soft [mask-image:linear-gradient(to_left,rgb(0_0_0)_20%,transparent)]" aria-hidden="true" />
      )}
      <div className="p-6 sm:p-8">
        <div className="grid items-center gap-6 sm:max-w-[62%] sm:grid-cols-[auto_minmax(0,1fr)]">
          <button
            className="group grid h-28 w-28 place-items-center overflow-hidden rounded-full border-4 border-white/90 bg-gradient-accent-soft shadow-panel"
            data-testid="role-detail-avatar"
            type="button"
            onClick={onOpenAssetsPage}
            aria-label="更换形象"
          >
            {previewAvatar ? (
              <img className="h-full w-full object-cover transition-transform duration-panel ease-out-soft motion-safe:group-hover:scale-105" src={toFileUrl(previewAvatar)} alt="" />
            ) : (
              <span className="font-display text-display text-ink-secondary" aria-hidden="true">{initial}</span>
            )}
          </button>
          <div className="grid min-w-0 gap-1.5">
            <input
              aria-label="角色名称"
              className={cx(roleIdentityInputClass, "font-display text-headline text-ink placeholder:text-ink-faint")}
              data-testid="edit-role-name"
              value={roleForm.name}
              placeholder="未命名角色"
              onChange={(event) => onUpdate((current) => ({ ...current, name: event.target.value }))}
            />
            <input
              aria-label="角色简介"
              className={cx(roleIdentityInputClass, "text-body text-ink-secondary placeholder:text-ink-faint")}
              data-testid="edit-role-description"
              value={roleForm.description}
              placeholder="添加一行角色简介"
              onChange={(event) => onUpdate((current) => ({ ...current, description: event.target.value }))}
            />
            <div className="mt-1 flex flex-wrap items-center gap-2">
              {currentMood ? (
                <span className={badgeClass} data-testid="role-detail-mood">
                  <Smiley className="h-3.5 w-3.5" aria-hidden="true" />
                  {currentMood}
                </span>
              ) : null}
              <button
                className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)}
                data-testid="open-role-assets-button"
                data-has-preview-avatar={previewAvatar ? "true" : "false"}
                type="button"
                onClick={onOpenAssetsPage}
              >
                <ImageSquare className="h-4 w-4" aria-hidden="true" />
                更换形象
              </button>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
