import { useEffect } from "react";
import { useLatestRef } from "../shared/useLatestRef";
import { resolveGlobalShortcut } from "./globalShortcuts";

type UseGlobalShortcutsArgs = {
  /** Off while a full-window surface (story) owns the keyboard. */
  enabled: boolean;
  onSearch: () => void;
  onSettings: () => void;
  /** The rail's view entries in rail order; Ctrl+1 selects the first. */
  views: ReadonlyArray<{ onSelect: () => void }>;
};

/**
 * Whether a dialog currently owns the keyboard. Shortcuts that navigate
 * underneath an open dialog (search, confirm, lightbox…) would leave it
 * floating over a different page, so they wait until it closes.
 */
export function isDialogOpen(root: ParentNode = document): boolean {
  return root.querySelector('[role="dialog"], [role="alertdialog"]') !== null;
}

/**
 * Installs the shell shortcuts (see `globalShortcuts.ts`) on `window`.
 * Handlers are the same guarded intents the rail buttons call, so the
 * unsaved-role-edits leave guard applies to a shortcut exactly as to a click.
 */
export function useGlobalShortcuts({ enabled, onSearch, onSettings, views }: UseGlobalShortcutsArgs) {
  const latest = useLatestRef({ onSearch, onSettings, views });

  useEffect(() => {
    if (!enabled) return undefined;
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.defaultPrevented) return;
      const action = resolveGlobalShortcut(event);
      if (!action) return;
      if (isDialogOpen()) return;
      const { onSearch: search, onSettings: settings, views: entries } = latest.current;
      if (action.kind === "view" && !entries[action.index]) return;
      event.preventDefault();
      if (action.kind === "search") search();
      else if (action.kind === "settings") settings();
      else entries[action.index]?.onSelect();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled, latest]);
}
