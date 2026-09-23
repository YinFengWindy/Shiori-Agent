import { SITE_PLACEHOLDER_COPY } from "./content/siteCopy";
import { AdvScreen } from "./screens/AdvScreen";
import { PlaceholderScreen } from "./screens/PlaceholderScreen";
import { SettingsModal } from "./screens/SettingsModal";
import { SoundToggle } from "./components/SoundToggle";
import { TitleScreen } from "./components/TitleScreen";
import { useSiteScreen } from "./screens/useSiteScreen";

/**
 * Site entry: wiring and screen dispatch only. `useSiteScreen` owns the
 * title/adv/character/gallery switch and the settings modal's open state;
 * #350 replaces the character/gallery placeholders in place. Sound lives in
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
      ) : (
        <PlaceholderScreen
          title={SITE_PLACEHOLDER_COPY[screen].title}
          body={SITE_PLACEHOLDER_COPY[screen].body}
          onBack={goToTitle}
        />
      )}
      <SoundToggle />
      {settingsOpen ? <SettingsModal onClose={closeSettings} /> : null}
    </div>
  );
}
