import { required } from "./dom";
import type { NarrativeAnchors } from "./narrativeModel";

/** The home page narrative's elements its scripts drive or read (NarrativeStage.astro). */
export interface NarrativeElements {
  readonly section: HTMLElement;
  /** The pinned one-viewport stage: its height is one step. */
  readonly stage: HTMLElement;
  /** The lines, in order. */
  readonly lines: readonly HTMLElement[];
  /** The download call closing the narrative. */
  readonly download: HTMLElement;
  /** The steps' anchors: each line's (named in its `data-anchor`), then the download call's id. */
  readonly anchors: NarrativeAnchors;
}

/**
 * The narrative on `document`, for the scripts that drive it (the narrative
 * itself) and follow it (the language switch, HomeLanguageSwitch.astro).
 */
export function narrativeElements(document: Document): NarrativeElements {
  const section = required(document.querySelector<HTMLElement>("[data-narrative]"), "the narrative");
  const stage = required(section.querySelector<HTMLElement>("[data-narrative-stage]"), "the narrative stage");
  const lines = [...section.querySelectorAll<HTMLElement>("[data-narrative-line]")];
  const download = required(stage.querySelector<HTMLElement>("[data-narrative-download]"), "the narrative's download call");
  const lineIds = lines.map((line, index) => required(line.dataset.anchor, `the anchor of narrative line ${index}`));
  return { section, stage, lines, download, anchors: { lineIds, downloadId: download.id } };
}
