import { useState } from "react";

/**
 * An editable copy of a stored value. The draft starts as `stored` and
 * starts over whenever `stored` changes (loaded, reread after a save);
 * `restart` begins again from a value the caller just stored, before the
 * reread arrives. `dirty` compares the draft with `stored` by `differs`.
 */
export function usePhoneDraft<T>(stored: T, differs: (draft: T, stored: T) => boolean) {
  const [state, setState] = useState({ base: stored, draft: stored });
  let current = state;
  if (state.base !== stored) {
    // Adjusting state while rendering: the draft follows a newly stored value in the same pass.
    current = { base: stored, draft: stored };
    setState(current);
  }
  return {
    draft: current.draft,
    dirty: differs(current.draft, stored),
    setDraft: (draft: T) => setState((previous) => ({ ...previous, draft })),
    restart: (value: T) => setState({ base: value, draft: value }),
  };
}
