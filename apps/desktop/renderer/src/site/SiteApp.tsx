import { SITE_PLACEHOLDER_COPY } from "./content/siteCopy";
import { PlaceholderScreen } from "./screens/PlaceholderScreen";
import { SettingsModal } from "./screens/SettingsModal";
import { TitleScreen } from "./components/TitleScreen";
import { useSiteScreen } from "./screens/useSiteScreen";

/**
 * Site entry: wiring and screen dispatch only. `useSiteScreen` owns the
 * title/adv/character/gallery switch and the settings modal's open state;
 * #348 and #350 replace the adv/character/gallery placeholders in place.
 */
export function SiteApp() {
  const { screen, settingsOpen, openScreen, goToTitle, openSettings, closeSettings } = useSiteScreen();

  return (
    <div className="site-root h-dvh min-h-0 text-site-ink">
      {screen === "title" ? (
        <TitleScreen onOpenScreen={openScreen} onOpenSettings={openSettings} />
      ) : (
        <PlaceholderScreen
          title={SITE_PLACEHOLDER_COPY[screen].title}
          body={SITE_PLACEHOLDER_COPY[screen].body}
          onBack={goToTitle}
        />
      )}
      {settingsOpen ? <SettingsModal onClose={closeSettings} /> : null}
    </div>
  );
}
