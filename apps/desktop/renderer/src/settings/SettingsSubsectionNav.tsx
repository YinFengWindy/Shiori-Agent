import { ArrowLeft } from "@phosphor-icons/react";
import { compactPressableClass, cx } from "../shared/styles";
import type { SettingsSubsection } from "./settingsPageTypes";

type SettingsSubsectionNavProps = {
  label: string;
  subsections: SettingsSubsection[];
  currentSubsectionId: string | null;
  onSelect: (subsectionId: string) => void;
  /**
   * Set on a nested detail page (a plugin's own settings under 「插件」):
   * the heading gets a back button returning to the parent list.
   */
  back?: { label: string; onBack: () => void };
};

/**
 * Shared section header + horizontal subtab strip. Used by both the
 * shared-draft ("editor") and standalone settings pages so there is exactly
 * one implementation of this markup (issue #230). The subtab strip itself
 * only renders once there is more than one subsection, matching every
 * single-subsection section's look (e.g. "关于").
 */
export function SettingsSubsectionNav({ label, subsections, currentSubsectionId, onSelect, back }: SettingsSubsectionNavProps) {
  return (
    <header className="mb-6">
      <div className="flex min-w-0 items-center gap-2">
        {back ? (
          <button
            type="button"
            className={cx(compactPressableClass, "-ml-2 grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink")}
            aria-label={`返回${back.label}`}
            title={`返回${back.label}`}
            onClick={back.onBack}
          >
            <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
          </button>
        ) : null}
        <h2 className="m-0 min-w-0 truncate font-display text-headline text-ink">{label}</h2>
      </div>
      {subsections.length > 1 ? (
        <nav className="mt-5 flex max-w-full gap-7 overflow-x-auto" aria-label="设置子区">
          {subsections.map((item) => (
            <button
              // No `focus:outline-none` here: styles.css keeps keyboard focus
              // visible through the global `:focus-visible` rule, and the
              // `after:` underline only marks the active tab.
              className={cx(
                "relative shrink-0 border-0 bg-transparent px-0 pb-2 text-body-sm transition",
                item.id === currentSubsectionId
                  ? "font-medium text-ink after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:rounded-full after:bg-accent"
                  : "text-ink-muted hover:text-ink-secondary",
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
