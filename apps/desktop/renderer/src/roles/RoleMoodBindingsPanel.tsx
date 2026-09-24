import { useEffect, useState } from "react";
import { roleFieldClass, roleFieldLabelClass } from "./roleEditorStyles";

type RoleMoodBindingsPanelProps = {
  /** The library image being bound; the field is off without one. */
  selectedAssetPath: string;
  /** The mood this image is bound to now; empty when unbound. */
  selectedMood: string;
  onSaveMoodBinding: (nextMood: string) => void;
};

/**
 * Binds the previewed image to a mood name: the chat shows it beside the
 * conversation while the role is in that mood. Saved on blur; clearing the
 * name unbinds the image.
 */
export function RoleMoodBindingsPanel({ selectedAssetPath, selectedMood, onSaveMoodBinding }: RoleMoodBindingsPanelProps) {
  const [draftMood, setDraftMood] = useState(selectedMood);

  useEffect(() => {
    setDraftMood(selectedMood);
  }, [selectedMood]);

  function handleMoodBlur(): void {
    const normalizedDraft = draftMood.trim();
    if (normalizedDraft === selectedMood.trim()) return;
    onSaveMoodBinding(normalizedDraft);
  }

  return (
    <label className={roleFieldLabelClass}>
      <span>对应心情</span>
      <input
        className={roleFieldClass}
        value={draftMood}
        onChange={(event) => setDraftMood(event.target.value.trimStart())}
        onBlur={handleMoodBlur}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
        }}
        placeholder="例如：平静"
        disabled={!selectedAssetPath}
      />
    </label>
  );
}
