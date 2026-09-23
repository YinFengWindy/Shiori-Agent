import { ArrowLeft } from "@phosphor-icons/react";
import { SITE_BACK_LABEL } from "../content/siteCopy";

interface PlaceholderScreenProps {
  title: string;
  body: string;
  onBack: () => void;
}

/**
 * Full-screen placeholder for a sub-screen that hasn't been built yet
 * (开始/人物/CG 鉴赏 — #348 and #350 replace these). Only the switching
 * chrome (back button) is real; Esc and right-click also return to the
 * title screen via `useSiteScreen`.
 */
export function PlaceholderScreen({ title, body, onBack }: PlaceholderScreenProps) {
  return (
    <div className="site-screen grid h-dvh min-h-0 place-items-center px-6 text-center">
      <div className="site-panel flex flex-col items-center gap-4 rounded-xl px-10 py-12">
        <h1 className="font-display text-headline text-site-ink">{title}</h1>
        <p className="text-body text-site-ink-muted">{body}</p>
        <button type="button" onClick={onBack} className="site-back-button mt-4 inline-flex items-center gap-2 rounded-md px-4 py-2 text-body-sm">
          <ArrowLeft size={16} aria-hidden="true" />
          {SITE_BACK_LABEL}
        </button>
      </div>
    </div>
  );
}
