import { SITE_LOGO_URL } from "../../content/siteAssets";

interface AdvChapterMarkProps {
  /** Label of the topic being explained, or null (opening / choices / closing). */
  topicLabel: string | null;
}

/**
 * Top-left corner mark on the ADV screen (desktop only): the Shiori logo,
 * with the current topic underneath while 吟风 is explaining it, like a
 * galgame chapter caption. Purely decorative beyond what the dialogue says.
 */
export function AdvChapterMark({ topicLabel }: AdvChapterMarkProps) {
  return (
    <div className="site-adv-chapter pointer-events-none absolute z-[1] hidden flex-col items-start gap-3 sm:flex" aria-hidden="true">
      <img src={SITE_LOGO_URL} alt="" className="site-title-logo w-[min(9rem,12vw)]" />
      <span key={topicLabel ?? ""} className="site-adv-chapter-label font-display">
        {topicLabel}
      </span>
    </div>
  );
}
