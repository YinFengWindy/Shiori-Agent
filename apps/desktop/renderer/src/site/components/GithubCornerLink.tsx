import { GithubLogo } from "@phosphor-icons/react";
import { SITE_GITHUB_LABEL, SITE_LINKS } from "../content/siteCopy";

/** Small corner GitHub icon link, always visible on the title screen. */
export function GithubCornerLink() {
  return (
    <a
      href={SITE_LINKS.github}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={SITE_GITHUB_LABEL}
      className="site-icon-button absolute right-4 top-4 z-10 rounded-md p-2 sm:right-6 sm:top-6"
    >
      <GithubLogo size={20} aria-hidden="true" />
    </a>
  );
}
