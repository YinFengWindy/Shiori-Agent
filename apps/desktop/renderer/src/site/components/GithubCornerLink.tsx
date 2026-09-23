import { GithubLogo } from "@phosphor-icons/react";
import { SITE_GITHUB_LABEL, SITE_LINKS } from "../content/siteCopy";

/** Corner GitHub icon link; placed by `SiteCornerLinks` on every screen. */
export function GithubCornerLink() {
  return (
    <a
      href={SITE_LINKS.github}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={SITE_GITHUB_LABEL}
      className="site-icon-button site-corner-chip rounded-full p-2.5"
    >
      <GithubLogo size={20} aria-hidden="true" />
    </a>
  );
}
