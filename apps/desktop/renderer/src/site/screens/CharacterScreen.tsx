import { useState } from "react";
import { CharacterOutfitPicker } from "../components/character/CharacterOutfitPicker";
import { CharacterPortrait } from "../components/character/CharacterPortrait";
import { CharacterProfileCard } from "../components/character/CharacterProfileCard";
import { SiteScene } from "../components/SiteScene";
import { SubScreenHeader } from "../components/SubScreenHeader";
import { CHARACTER_PROFILE } from "../content/characterProfile";
import { SITE_CHARACTER_COPY } from "../content/siteCopy";

interface CharacterScreenProps {
  onBack: () => void;
}

/**
 * 「人物」: 吟风's galgame-style character profile over the room scene — her
 * framed standing art, 换装 thumbnails switching between the three outfits,
 * and the profile card. Wiring only; the grid areas in site.css place the
 * art, card and outfit picker for desktop and mobile.
 */
export function CharacterScreen({ onBack }: CharacterScreenProps) {
  const [outfit, setOutfit] = useState(0);
  const outfits = CHARACTER_PROFILE.outfits;

  return (
    <div className="site-screen site-subscreen relative flex h-dvh min-h-0 flex-col overflow-hidden">
      <SiteScene />
      <div className="site-subscreen-veil pointer-events-none absolute inset-0" aria-hidden="true" />
      <SubScreenHeader title={SITE_CHARACTER_COPY.title} eyebrow={SITE_CHARACTER_COPY.eyebrow} onBack={onBack} />
      <main className="site-character-layout relative grid min-h-0 flex-1">
        <div className="site-character-art-area min-h-0">
          <CharacterPortrait outfits={outfits} index={outfit} />
        </div>
        <div className="site-character-profile-area min-h-0">
          <CharacterProfileCard />
        </div>
        <div className="site-character-outfits-area min-h-0">
          <CharacterOutfitPicker outfits={outfits} index={outfit} onSelect={setOutfit} />
        </div>
      </main>
    </div>
  );
}
