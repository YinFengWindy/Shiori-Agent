import { useState } from "react";
import type { DesktopUpdateState } from "../../../src/updateContract.js";
import { aboutIdleLines, aboutUpdateLines, pickMascotLine, type MascotLine } from "../shared/mascot/mascotLines";

type UpdatePhase = DesktopUpdateState["phase"];

const updateReady = (phase: UpdatePhase | undefined) => phase === "downloading" || phase === "downloaded";

/**
 * What 吟风 says about an update phase change on 设置 › 关于, or null to
 * keep her current line. A found update is announced however the page
 * learns of it (also on first load); 「已是最新」 only once a check the page
 * saw starting finishes, so reopening 关于 after an earlier check still opens
 * with a random line. A failed update (phase `error`) gets her worried line.
 */
export function aboutLineForPhaseChange(previous: UpdatePhase | undefined, next: UpdatePhase | undefined): MascotLine | null {
  if (previous === next) return null;
  if (updateReady(next) && !updateReady(previous)) return aboutUpdateLines.available;
  if (next === "current" && previous !== undefined) return aboutUpdateLines.current;
  // She is on stage here, so the failure is hers to say (the inline error below stays plain).
  if (next === "error") return aboutUpdateLines.failed;
  return null;
}

/**
 * 吟风's line on 设置 › 关于: a random idle line on open, another one (never
 * the same twice in a row) with every click on her, and the update check's
 * outcome when it changes.
 */
export function useAboutMascotLine(phase: UpdatePhase | undefined) {
  const [line, setLine] = useState(() => pickMascotLine(aboutIdleLines));
  // Previous-prop pattern: react to the phase change during render, no effect round-trip.
  const [seenPhase, setSeenPhase] = useState(phase);
  if (phase !== seenPhase) {
    setSeenPhase(phase);
    const said = aboutLineForPhaseChange(seenPhase, phase);
    if (said) setLine(said);
  }
  return {
    line,
    /** Click on her: the next idle line. */
    next: () => setLine((current) => pickMascotLine(aboutIdleLines, current)),
  };
}
