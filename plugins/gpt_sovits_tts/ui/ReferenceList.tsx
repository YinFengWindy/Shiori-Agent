import { useState } from "react";
import { usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { RoleVoice } from "../shared/contracts";
import { CustomMoodForm } from "./CustomMoodForm";
import { pendingCatalogMoods, setVoiceReference, voiceReference } from "./emotionReferenceState";
import { ReferenceRow } from "./ReferenceRow";
import { useReferenceImport } from "./useReferenceImport";

type VoiceChange = (change: (current: RoleVoice) => RoleVoice) => void;

type ReferenceListProps = {
  roleId: string;
  client: PluginRpcClient;
  draft: RoleVoice;
  moodCatalog: readonly string[];
  disabled: boolean;
  /** Typing edits: saved once they pause. */
  onUpdate: VoiceChange;
  /** Discrete edits (import, delete, language): saved at once. */
  onCommit: VoiceChange;
  /** Preview of one mood; the empty mood is the default reference. */
  onPreview(mood: string): void;
  previewDisabled: boolean;
};

/**
 * The default reference, then each configured mood, then catalog moods still
 * without audio, as compact rows of which at most one is expanded.
 */
export function ReferenceList({ roleId, client, draft, moodCatalog, disabled, onUpdate, onCommit, onPreview, previewDisabled }: ReferenceListProps) {
  const host = usePluginHostServices();
  const importer = useReferenceImport(client, roleId);
  const [expanded, setExpanded] = useState<string | null>(null);
  const configured = Object.keys(draft.moods);
  const rows = [["", "默认参考"], ...configured.map((name) => [name, name]), ...pendingCatalogMoods(moodCatalog, configured).map((name) => [name, name])];
  const blocked = disabled || importer.busy !== null;

  // An import keeps the transcript and language of the audio it replaces.
  async function importFor(mood: string) {
    const imported = await importer.importFor(mood);
    if (!imported) return false;
    onCommit((current) => {
      const previous = voiceReference(current, mood);
      return setVoiceReference(current, mood, { asset: imported.asset, duration: imported.duration, prompt_text: previous?.prompt_text ?? "", prompt_lang: previous?.prompt_lang ?? "zh" });
    });
    return true;
  }

  return <section className="grid gap-3" aria-label="参考音频">
    <ul className="m-0 grid list-none gap-2 p-0">
      {rows.map(([mood, title]) => {
        const value = voiceReference(draft, mood);
        return <ReferenceRow key={`${mood === "" ? "default" : "mood"}:${mood}`} title={title} value={value}
          expanded={expanded === mood && value !== null} disabled={blocked} importing={importer.busy === mood}
          previewDisabled={previewDisabled || !draft.default}
          onToggle={() => setExpanded((current) => current === mood ? null : mood)}
          onImport={() => void importFor(mood)}
          onPreview={() => onPreview(mood)}
          onDelete={() => onCommit((current) => setVoiceReference(current, mood, null))}
          onTranscript={(text) => onUpdate((current) => { const previous = voiceReference(current, mood); return previous ? setVoiceReference(current, mood, { ...previous, prompt_text: text }) : current; })}
          onLanguage={(language) => onCommit((current) => { const previous = voiceReference(current, mood); return previous ? setVoiceReference(current, mood, { ...previous, prompt_lang: language }) : current; })} />;
      })}
    </ul>
    <CustomMoodForm existing={configured} disabled={blocked} importing={importer.busy !== null && !rows.some(([mood]) => mood === importer.busy)} onImport={importFor} />
    {importer.error ? <host.ui.InlineError message={importer.error} /> : null}
  </section>;
}
