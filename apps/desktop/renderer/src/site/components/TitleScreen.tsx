import { SITE_LOGO_URL, titleArtwork } from "../content/siteAssets";
import type { SiteScreenId } from "../content/siteCopy";
import { useTitleArtSelection } from "../titleArt/useTitleArtSelection";
import { GithubCornerLink } from "./GithubCornerLink";
import { SiteDecorations } from "./SiteDecorations";
import { TitleArtwork } from "./TitleArtwork";
import { TitleArtworkDots } from "./TitleArtworkDots";
import { TitleMenu } from "./TitleMenu";

interface TitleScreenProps {
  onOpenScreen: (screen: Exclude<SiteScreenId, "title">) => void;
  onOpenSettings: () => void;
}

/**
 * The galgame title screen: night gradient + faint star/petal decoration,
 * full-bleed standing art (bottom-right on desktop, full-bleed behind the
 * menu on narrow screens — see TitleArtwork/site.css for the feathering),
 * logo + vertical menu + dot indicators on top, a small GitHub icon in the
 * corner. The whole screen is exactly one viewport tall, no scrolling.
 *
 * The title art's random-index selection lives here (not inside
 * TitleArtwork) so both the art layer and the dot indicators — which sit
 * next to the menu rather than guessing an overlay position against the
 * art's responsive sizing — share the same state.
 */
export function TitleScreen({ onOpenScreen, onOpenSettings }: TitleScreenProps) {
  const { index, advance, select } = useTitleArtSelection(titleArtwork.length);

  return (
    <div className="site-screen site-title-screen relative h-dvh min-h-0 overflow-hidden">
      <SiteDecorations />
      <TitleArtwork index={index} onAdvance={advance} />
      <GithubCornerLink />
      <div className="site-title-content relative z-[1] flex h-full min-h-0 flex-col justify-end gap-3 px-6 pb-6 pt-10 sm:justify-center sm:gap-7 sm:pb-0 sm:pt-0">
        <img className="site-title-logo w-[min(9rem,40vw)] sm:w-[min(15rem,22vw)]" src={SITE_LOGO_URL} alt="" />
        <span className="site-ornament-line" aria-hidden="true" />
        <TitleMenu onOpenScreen={onOpenScreen} onOpenSettings={onOpenSettings} />
        <TitleArtworkDots index={index} onSelect={select} />
      </div>
      <h1 className="sr-only">栞 / SHIORI</h1>
    </div>
  );
}
