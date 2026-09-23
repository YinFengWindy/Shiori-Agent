import { SITE_LOGO_URL, titleSprites } from "../content/siteAssets";
import type { SiteScreenId } from "../content/siteCopy";
import { useTitleArtSelection } from "../titleArt/useTitleArtSelection";
import { SiteDecorations } from "./SiteDecorations";
import { SiteScene } from "./SiteScene";
import { TitleArtwork } from "./TitleArtwork";
import { TitleArtworkDots } from "./TitleArtworkDots";
import { TitleMenu } from "./TitleMenu";

interface TitleScreenProps {
  onOpenScreen: (screen: Exclude<SiteScreenId, "title">) => void;
  onOpenSettings: () => void;
}

/**
 * The galgame title screen: the time-of-day scene full-bleed, a few
 * drifting petals, 吟风's cut-out sprite standing on the right (centred
 * behind the menu on narrow screens), and the logo + vertical menu + dot
 * indicators on a frosted lavender-white panel so they read clearly on the
 * scene. The corner icons are global (`SiteCornerLinks` in SiteApp). The
 * whole screen is exactly one viewport tall, no scrolling.
 *
 * The sprite's random-index selection lives here (not inside TitleArtwork)
 * so both the sprite layer and the dot indicators share the same state.
 */
export function TitleScreen({ onOpenScreen, onOpenSettings }: TitleScreenProps) {
  const { index, advance, select } = useTitleArtSelection(titleSprites.length);

  return (
    <div className="site-screen site-title-screen relative h-dvh min-h-0 overflow-hidden">
      <SiteScene />
      <TitleArtwork index={index} onAdvance={advance} />
      <SiteDecorations />
      <div className="site-title-content pointer-events-none relative z-[1] flex h-full min-h-0 flex-col justify-end sm:justify-center">
        <div className="site-title-panel pointer-events-auto flex flex-col items-center gap-3 sm:items-start sm:gap-5">
          <img className="site-title-logo w-[min(7.5rem,34vw)] sm:w-[min(13rem,20vw)]" src={SITE_LOGO_URL} alt="" />
          <span className="site-ornament-line" aria-hidden="true" />
          <TitleMenu onOpenScreen={onOpenScreen} onOpenSettings={onOpenSettings} />
          <TitleArtworkDots index={index} onSelect={select} />
        </div>
      </div>
      <h1 className="sr-only">栞 / SHIORI</h1>
    </div>
  );
}
