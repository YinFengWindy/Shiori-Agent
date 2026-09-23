import { GithubCornerLink } from "./GithubCornerLink";
import { SoundToggle } from "./SoundToggle";

/**
 * The fixed top-right icon cluster shown on every screen: the sound toggle
 * and the GitHub link, side by side. It sits above the screens (sub-screen
 * headers and the ADV event CG leave room for it, see `--site-corner-*` in
 * site.css) and below full-screen overlays (settings, backlog, CG lightbox).
 */
export function SiteCornerLinks() {
  return (
    <div className="site-corner-links fixed z-20 flex items-center gap-2">
      <SoundToggle />
      <GithubCornerLink />
    </div>
  );
}
