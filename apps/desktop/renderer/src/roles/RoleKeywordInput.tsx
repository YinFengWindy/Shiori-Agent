import { useState } from "react";
import { roleFieldClass, roleFieldLabelClass } from "./roleEditorStyles";

type RoleKeywordInputProps = {
  label: string;
  keywords: string[];
  onChange: (keywords: string[]) => void;
};

function parseKeywords(value: string) {
  return [...new Set(value.split(",").map((keyword) => keyword.trim()).filter(Boolean))];
}

/** Keeps keyword punctuation editable while updating the shared role draft immediately. */
export function RoleKeywordInput({ label, keywords, onChange }: RoleKeywordInputProps) {
  const source = keywords.join(", ");
  const [draft, setDraft] = useState(source);
  // External role changes reset the input; matching semantic updates retain typed punctuation.
  if (draft !== source && parseKeywords(draft).join(", ") !== source) setDraft(source);

  function updateDraft(value: string) {
    setDraft(value);
    const next = parseKeywords(value);
    if (next.join(", ") !== source) onChange(next);
  }

  function normalizeDraft() {
    setDraft(parseKeywords(draft).join(", "));
  }

  return (
    <label className={roleFieldLabelClass}>
      <span>{label}</span>
      <input
        className={roleFieldClass}
        value={draft}
        onChange={(event) => updateDraft(event.target.value)}
        onBlur={normalizeDraft}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.nativeEvent.isComposing) {
            event.preventDefault();
            normalizeDraft();
          }
        }}
      />
    </label>
  );
}
