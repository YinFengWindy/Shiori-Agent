import { useCallback, useEffect, useState } from "react";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { errorMessage, feedback } from "../../../apps/desktop/renderer/src/shared/feedback/feedbackStore";
import type { PromptTagWorkspaceSectionId } from "./novelAiPageStore";
import type { PromptTagEntry } from "./types";

/** A new entry's starting fields. */
export const emptyPromptTagDraft: PromptTagEntry = {
  id: "", name: "", enabled: true, category: "composition", match_terms: [], positive_tags: [], negative_tags: [], rating: "general", image_path: "",
};

function draftSignature(draft: PromptTagEntry): string {
  return JSON.stringify({ ...draft, id: draft.id.trim(), name: draft.name.trim(), category: draft.category.trim() });
}

/** Why a draft cannot be saved yet, or "" when it can. */
export function validatePromptTagDraft(draft: PromptTagEntry): string {
  if (!draft.id.trim() || !draft.name.trim() || !draft.category.trim()) return "标识、名称和分类不能为空";
  if (!draft.match_terms.length || !draft.positive_tags.length) return "至少填写一个匹配词和一个正向标签";
  return "";
}

/**
 * Loads the prompt-tag catalog and owns the editor draft: open, create,
 * save and delete, routing between the list and the editor through the
 * shared workspace section.
 */
export function usePromptTagLibrary(
  client: PluginRpcClient,
  bridgeReady: boolean,
  section: PromptTagWorkspaceSectionId,
  onOpenSection: (section: PromptTagWorkspaceSectionId) => void,
) {
  const [entries, setEntries] = useState<PromptTagEntry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<PromptTagEntry>(emptyPromptTagDraft);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const loadEntries = useCallback(async (): Promise<PromptTagEntry[]> => {
    const payload = await client.call<{ entries: PromptTagEntry[] }>("prompt_tags.list", {});
    const next = Array.isArray(payload.entries) ? payload.entries : [];
    setEntries(next);
    setLoaded(true);
    return next;
  }, [client]);

  useEffect(() => {
    if (!bridgeReady) return;
    loadEntries().catch((loadError: unknown) => feedback.error("提示词库加载失败", { detail: errorMessage(loadError) }));
  }, [bridgeReady, loadEntries]);

  // Entering "create" (from the list's button) always starts from a blank draft.
  useEffect(() => {
    if (section !== "create") return;
    setDraft(emptyPromptTagDraft);
    setSelectedId("");
    setError("");
  }, [section]);

  const original = selectedId ? entries.find((entry) => entry.id === selectedId) ?? emptyPromptTagDraft : emptyPromptTagDraft;

  async function save(): Promise<void> {
    const payload = { ...draft, id: draft.id.trim(), name: draft.name.trim(), category: draft.category.trim() };
    const invalid = validatePromptTagDraft(payload);
    if (invalid) {
      setError(invalid);
      return;
    }
    setSaving(true);
    setError("");
    try {
      await client.call("prompt_tags.upsert", payload);
      setSelectedId(payload.id);
      setDraft(payload);
      onOpenSection("detail");
      await loadEntries();
      feedback.success("提示词已保存");
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string): Promise<void> {
    await client.call("prompt_tags.delete", { id });
    if (selectedId === id) {
      setSelectedId("");
      setDraft(emptyPromptTagDraft);
      onOpenSection("list");
    }
    await loadEntries();
  }

  function open(entry: PromptTagEntry): void {
    setDraft(entry);
    setSelectedId(entry.id);
    setError("");
    onOpenSection("detail");
  }

  return {
    entries,
    loaded,
    draft,
    error,
    saving,
    creating: section === "create",
    dirty: draftSignature(draft) !== draftSignature(original),
    setDraft,
    save,
    remove,
    open,
    reset: () => setDraft(original),
  };
}
