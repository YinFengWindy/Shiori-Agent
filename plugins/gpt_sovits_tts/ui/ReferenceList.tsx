import { useState } from "react";
import { usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { RoleVoice } from "../shared/contracts";
import { CustomMoodForm } from "./CustomMoodForm";
import { customImportBusy, patchVoiceReference, pendingCatalogMoods, setVoiceReference, voiceReference } from "./emotionReferenceState";
import { ReferenceRow } from "./ReferenceRow";
import { useReferenceImport } from "./useReferenceImport";
import type { RoleVoiceAutosave } from "./useRoleVoice";

type ReferenceListProps = {
  roleId: string;
  client: PluginRpcClient;
  /** The loaded draft; typing goes through `update` (saved once it pauses), discrete edits through `commit` (saved at once). */
  voice: Pick<RoleVoiceAutosave, "update" | "commit"> & { draft: RoleVoice };
  moodCatalog: readonly string[];
  disabled: boolean;
  /** Preview of one mood; the empty mood is the default reference. */
  onPreview(mood: string): void;
  previewDisabled: boolean;
};

/**
 * The default reference, then each configured mood, then catalog moods still
 * without audio, as compact rows of which at most one is expanded.
 */
export function ReferenceList({ roleId, client, voice, moodCatalog, disabled, onPreview, previewDisabled }: ReferenceListProps) {
  const host = usePluginHostServices();
  const importer = useReferenceImport(client, roleId);
  const [expanded, setExpanded] = useState<string | null>(null);
  const { draft } = voice;
  const configured = Object.keys(draft.moods);
  const pending = pendingCatalogMoods(moodCatalog, configured);
  const rowMoods = ["", ...configured, ...pending];
  const blocked = disabled || importer.busy !== null;

  async function importFor(mood: string) {
    const imported = await importer.importFor(mood);
    if (imported) voice.commit((current) => patchVoiceReference(current, mood, imported));
    return imported !== null;
  }

  return <section className="grid gap-3" aria-label="参考音频">
    <ul className="m-0 grid list-none gap-2 p-0">
      {rowMoods.map((mood) => {
        const value = voiceReference(draft, mood);
        return <ReferenceRow key={mood === "" ? "default" : `mood:${mood}`} title={mood === "" ? "默认参考" : mood} value={value}
          expanded={expanded === mood && value !== null} disabled={blocked} importing={importer.busy === mood}
          previewDisabled={previewDisabled || !draft.default}
          onToggle={() => setExpanded((current) => current === mood ? null : mood)}
          onImport={() => void importFor(mood)}
          onPreview={() => onPreview(mood)}
          onDelete={() => voice.commit((current) => setVoiceReference(current, mood, null))}
          onTranscript={(prompt_text) => voice.update((current) => patchVoiceReference(current, mood, { prompt_text }))}
          onLanguage={(prompt_lang) => voice.commit((current) => patchVoiceReference(current, mood, { prompt_lang }))} />;
      })}
    </ul>
    {/* Catalog moods already have their own row, so the custom form refuses their names too. */}
    <CustomMoodForm existing={[...configured, ...pending]} disabled={blocked} importing={customImportBusy(importer.busy, rowMoods)} onImport={importFor} />
    {importer.error ? <host.ui.InlineError message={importer.error} /> : null}
  </section>;
}
