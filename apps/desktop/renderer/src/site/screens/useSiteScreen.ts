import { useCallback, useEffect, useState } from "react";
import type { SiteScreenId } from "../content/siteCopy";

/**
 * The site's whole-screen switching state: which of title/adv/character/
 * gallery is showing, plus the settings modal's open state layered on top of
 * whichever screen is active. Back button, Esc and right-click all return to
 * the title screen (or close the settings modal first if it is open); #348
 * and #350 replace the adv/character/gallery placeholders without touching
 * this module.
 */
export function useSiteScreen() {
  const [screen, setScreen] = useState<SiteScreenId>("title");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const openScreen = useCallback((next: Exclude<SiteScreenId, "title">) => {
    setScreen(next);
  }, []);
  const goToTitle = useCallback(() => setScreen("title"), []);
  const openSettings = useCallback(() => setSettingsOpen(true), []);
  const closeSettings = useCallback(() => setSettingsOpen(false), []);

  // Esc and right-click (contextmenu) close the settings modal first;
  // otherwise they return to the title screen. Right-click never opens the
  // native menu off the title screen, matching galgame convention. Overlays
  // owned by a screen (the ADV backlog) stop these events themselves.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (settingsOpen) {
        closeSettings();
        return;
      }
      if (screen !== "title") goToTitle();
    }
    function handleContextMenu(event: MouseEvent) {
      if (screen === "title" && !settingsOpen) return;
      event.preventDefault();
      if (settingsOpen) {
        closeSettings();
        return;
      }
      goToTitle();
    }
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("contextmenu", handleContextMenu);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("contextmenu", handleContextMenu);
    };
  }, [screen, settingsOpen, goToTitle, closeSettings]);

  return { screen, settingsOpen, openScreen, goToTitle, openSettings, closeSettings };
}
