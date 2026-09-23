import type { SiteScreenId } from "../content/siteCopy";
import { GithubCornerLink } from "./GithubCornerLink";
import { SiteDecorations } from "./SiteDecorations";
import { TitleArtwork } from "./TitleArtwork";
import { TitleMenu } from "./TitleMenu";

/** Relative to the built site's own output root (see vite.site.config.ts). */
const SITE_LOGO_URL = "./assets/branding/shiori-title-logo.png";

interface TitleScreenProps {
  onOpenScreen: (screen: Exclude<SiteScreenId, "title">) => void;
  onOpenSettings: () => void;
}

/**
 * The galgame title screen: night gradient + faint star/petal decoration,
 * logo and vertical menu on the left, standing art with dot indicators on
 * the right, a small GitHub icon in the corner. On narrow screens the art
 * sits full-bleed behind the menu, which overlays the bottom.
 */
export function TitleScreen({ onOpenScreen, onOpenSettings }: TitleScreenProps) {
  return (
    <div className="site-screen site-title-screen relative h-dvh min-h-0 overflow-hidden">
      <SiteDecorations />
      <GithubCornerLink />
      <div className="site-title-layout relative z-[1] flex h-full min-h-0 flex-col-reverse sm:flex-row">
        <div className="site-title-panel flex flex-col justify-center gap-8 px-6 py-8 sm:w-[22rem] sm:px-10 sm:py-12">
          <img className="site-title-logo w-[min(14rem,60vw)]" src={SITE_LOGO_URL} alt="" />
          <span className="site-ornament-line" aria-hidden="true" />
          <TitleMenu onOpenScreen={onOpenScreen} onOpenSettings={onOpenSettings} />
        </div>
        <div className="site-title-art-area relative flex flex-1 items-end justify-center sm:items-center sm:justify-end sm:pr-12">
          <TitleArtwork />
        </div>
      </div>
      <h1 className="sr-only">栞 / SHIORI</h1>
    </div>
  );
}
