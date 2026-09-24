import { useState } from "react";
import { useAdvDialogue } from "../adv/useAdvDialogue";
import { useAdvKeyboard } from "../../shared/adv/useAdvKeyboard";
import { AdvEventCg, AdvSprite } from "../components/adv/AdvArtwork";
import { AdvBacklog } from "../components/adv/AdvBacklog";
import { AdvChapterMark } from "../components/adv/AdvChapterMark";
import { AdvChoiceList } from "../components/adv/AdvChoiceList";
import { AdvControls } from "../components/adv/AdvControls";
import { AdvDialogueBox } from "../../shared/adv/AdvDialogueBox";
import { SceneBackdrop } from "../../shared/scene/SceneBackdrop";
import { ADV_SCRIPT } from "../content/advScript";
import { SITE_ADV_COPY } from "../content/siteCopy";
import { usePrefersReducedMotion } from "../../shared/usePrefersReducedMotion";
import { avatarImage } from "../content/siteAssets";
import { pageLoadScenePhase } from "../scene/pageLoadScenePhase";
import { TEXT_SPEED_MS_PER_CHAR } from "../prefs/sitePrefs";
import { useSitePrefs } from "../prefs/useSitePrefs";
import { useLineAdvanceSfx } from "../sound/useSound";

interface AdvScreenProps {
  /** Settings modal is open on top: pause typing, auto mode and key handling. */
  settingsOpen: boolean;
  onOpenSettings: () => void;
  onExit: () => void;
}

/**
 * 「开始」: a standard galgame ADV — the time-of-day scene, 吟风's sprite
 * centre-right, the dialogue box at the bottom; a topic swaps the sprite for
 * its event CG above the box. The stage is a two-row grid: row 1 holds the
 * event CG and (in the choice phase) the choice list, row 2 the dialogue
 * box, so the CG always fits whatever height the box leaves. Wiring only — the dialogue logic is `adv/advModel.ts` (driven by
 * `useAdvDialogue`), the words are `content/advScript.ts`.
 */
export function AdvScreen({ settingsOpen, onOpenSettings, onExit }: AdvScreenProps) {
  const { prefs } = useSitePrefs();
  const reducedMotion = usePrefersReducedMotion();
  const [backlogOpen, setBacklogOpen] = useState(false);
  const paused = settingsOpen || backlogOpen;
  const adv = useAdvDialogue({
    script: ADV_SCRIPT,
    msPerChar: TEXT_SPEED_MS_PER_CHAR[prefs.textSpeed],
    reducedMotion,
    paused,
    onEnd: onExit,
  });
  useAdvKeyboard(!paused && adv.phase === "line", adv.click);
  useLineAdvanceSfx(adv.lineKey);

  const speaking = adv.line !== null;

  return (
    <div className="site-screen site-adv-screen relative h-dvh min-h-0 overflow-hidden">
      <h1 className="sr-only">{SITE_ADV_COPY.screenLabel}</h1>
      <SceneBackdrop phase={pageLoadScenePhase} />
      <AdvSprite art={adv.art} />
      <AdvChapterMark topicLabel={adv.topicLabel} />
      {speaking ? (
        <button type="button" onClick={adv.click} aria-label={SITE_ADV_COPY.advance} className="site-adv-advance absolute inset-0 z-[1] h-full w-full" />
      ) : null}
      <div className="site-adv-stage pointer-events-none relative z-[2] grid h-full min-h-0">
        <AdvEventCg art={adv.art} />
        {adv.phase === "choice" ? (
          <div className="site-adv-choices-wrap pointer-events-auto flex min-h-0 items-center justify-center">
            <AdvChoiceList choices={adv.choices} onChoose={adv.choose} />
          </div>
        ) : null}
        <AdvDialogueBox
          className="site-adv-box"
          speaker={ADV_SCRIPT.speaker}
          avatarSrc={avatarImage.src}
          text={adv.line ?? adv.prompt}
          shownChars={speaking ? adv.shownChars : adv.prompt.length}
          waiting={speaking && adv.complete}
          controls={
            <AdvControls
              autoMode={adv.autoMode}
              canSkip={speaking}
              onToggleAuto={adv.toggleAuto}
              onSkip={adv.skip}
              onOpenBacklog={() => setBacklogOpen(true)}
              onOpenSettings={onOpenSettings}
              onExit={onExit}
            />
          }
        />
      </div>
      {backlogOpen ? <AdvBacklog speaker={ADV_SCRIPT.speaker} entries={adv.backlog} onClose={() => setBacklogOpen(false)} /> : null}
    </div>
  );
}
