import { AdvScreen } from "./screens/AdvScreen";
import { CharacterScreen } from "./screens/CharacterScreen";
import { GalleryScreen } from "./screens/GalleryScreen";
import { SettingsModal } from "./screens/SettingsModal";
import { SoundToggle } from "./components/SoundToggle";
import { TitleScreen } from "./components/TitleScreen";
import { useSiteScreen } from "./screens/useSiteScreen";

/**
 * Site entry: wiring and screen dispatch only. `useSiteScreen` owns the
 * title/adv/character/gallery switch and the settings modal's open state;
 * the 人物 / CG 鉴赏 screens are self-contained. Sound lives in
 * `<SoundProvider>` (mounted in main.tsx); the speaker toggle is global.
 */
export function SiteApp() {
  const { screen, settingsOpen, openScreen, goToTitle, openSettings, closeSettings } = useSiteScreen();

  return (
    <div className="site-root h-dvh min-h-0 text-site-ink">
      {screen === "title" ? (
        <TitleScreen onOpenScreen={openScreen} onOpenSettings={openSettings} />
      ) : screen === "adv" ? (
        <AdvScreen settingsOpen={settingsOpen} onOpenSettings={openSettings} onExit={goToTitle} />
      ) : screen === "character" ? (
        <CharacterScreen onBack={goToTitle} />
      ) : (
        <GalleryScreen onBack={goToTitle} />
      )}
      <SoundToggle />
      {settingsOpen ? <SettingsModal onClose={closeSettings} /> : null}
    </div>
  );
}
