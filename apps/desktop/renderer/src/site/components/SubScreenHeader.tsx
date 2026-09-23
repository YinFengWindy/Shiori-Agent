import type { ReactNode } from "react";
import { ArrowLeft } from "@phosphor-icons/react";
import { SITE_BACK_LABEL } from "../content/siteCopy";
import { useButtonSfx } from "../sound/useSound";

interface SubScreenHeaderProps {
  title: string;
  /** Small latin caption above the title (CHARACTER / GALLERY). */
  eyebrow: string;
  onBack: () => void;
  /** Extra content after the title, e.g. the gallery's collected count. */
  children?: ReactNode;
}

/**
 * Top bar shared by the 人物 and CG 鉴赏 screens: the 返回标题 button and the
 * screen's `<h1>`. Esc and right-click also return to the title via
 * `useSiteScreen`. Leaves the top-right corner free for the corner icons (`SiteCornerLinks`).
 */
export function SubScreenHeader({ title, eyebrow, onBack, children }: SubScreenHeaderProps) {
  const { hover, click } = useButtonSfx();
  return (
    <header className="site-subscreen-header flex min-w-0 items-center gap-3 sm:gap-5">
      <button
        type="button"
        onPointerEnter={hover}
        onClick={() => {
          click();
          onBack();
        }}
        className="site-back-button site-subscreen-back inline-flex shrink-0 items-center gap-1.5 rounded-full text-body-sm"
      >
        <ArrowLeft size={16} aria-hidden="true" />
        {/* Phones show a round arrow chip; the label stays as its accessible name. */}
        <span className="sr-only sm:not-sr-only">{SITE_BACK_LABEL}</span>
      </button>
      <div className="flex min-w-0 items-baseline gap-3">
        <h1 className="site-subscreen-title font-display">
          <span className="site-subscreen-eyebrow" aria-hidden="true">
            {eyebrow}
          </span>
          {title}
        </h1>
        {children}
      </div>
    </header>
  );
}
