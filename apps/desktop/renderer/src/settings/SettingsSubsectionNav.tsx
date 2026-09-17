import { cx } from "../shared/styles";
import type { SettingsSubsection } from "./settingsPageTypes";

type SettingsSubsectionNavProps = {
  label: string;
  subsections: SettingsSubsection[];
  currentSubsectionId: string | null;
  onSelect: (subsectionId: string) => void;
};

/**
 * Shared section header + horizontal subtab strip. Used by both the
 * shared-draft ("editor") and standalone settings pages so there is exactly
 * one implementation of this markup (issue #230) — previously the
 * standalone branch skipped both the header and the subtab nav entirely,
 * which is why a multi-subsection standalone section (「插件」, once its
 * plugin subtabs nest under it) had no visible way to switch between them.
 * The subtab strip itself only renders once there is more than one
 * subsection, matching every existing single-subsection section's look
 * (e.g. "关于").
 */
export function SettingsSubsectionNav({ label, subsections, currentSubsectionId, onSelect }: SettingsSubsectionNavProps) {
  return (
    <header className="mb-6">
      <h2 className="m-0 font-display text-headline text-ink">{label}</h2>
      {subsections.length > 1 ? (
        <nav className="mt-7 flex max-w-full gap-7 overflow-x-auto" aria-label="设置子区">
          {subsections.map((item) => (
            <button
              // `focus:outline-none` opts this keyboard-reachable tab out of
              // the global focus-ring treatment (styles.css's shared
              // input/textarea/select:focus rule doesn't apply to a
              // <button> anyway). Carried over verbatim from the pre-#230
              // editor-only header this component replaces, not introduced
              // here — the active tab's permanent `after:` underline is the
              // only visible state indicator once this is removed, which is
              // weaker than a focus ring for a keyboard user tabbing through
              // an *inactive* button. Flagging rather than silently
              // inheriting it, per this repo's rule that a focus opt-out
              // needs its reasoning written down.
              className={cx(
                "relative shrink-0 border-0 bg-transparent px-0 pb-2 text-body-sm transition focus:outline-none",
                item.id === currentSubsectionId
                  ? "font-medium text-ink after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-accent"
                  : "text-ink-faint hover:text-ink-secondary",
              )}
              key={item.id}
              type="button"
              aria-current={item.id === currentSubsectionId ? "page" : undefined}
              onClick={() => onSelect(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      ) : null}
    </header>
  );
}
