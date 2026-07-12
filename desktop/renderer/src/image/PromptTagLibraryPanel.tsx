import { useCallback, useEffect, useState } from "react";
import { PromptTagEntryEditor, type PromptTagDraft } from "./PromptTagEntryEditor";
import type { PromptTagEntry } from "./types";

type PromptTagLibraryPanelProps = {
  bridgeReady: boolean;
};

const emptyDraft: PromptTagDraft = {
  id: "",
  name: "",
  enabled: true,
  category: "composition",
  match_terms: [],
  positive_tags: [],
  negative_tags: [],
  rating: "general",
};

/** Manages the editable prompt-tag catalog inside the image studio sidebar. */
export function PromptTagLibraryPanel({ bridgeReady }: PromptTagLibraryPanelProps) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<PromptTagEntry[]>([]);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [draft, setDraft] = useState<PromptTagDraft>(emptyDraft);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const categories = [...new Set(entries.map((entry) => entry.category))].sort();
  const visibleEntries = categoryFilter
    ? entries.filter((entry) => entry.category === categoryFilter)
    : entries;

  const loadEntries = useCallback(async (): Promise<void> => {
    const response = await window.miraDesktop.invoke({
      method: "novelai.prompt_tags.list",
      payload: {},
    });
    if (response.error) {
      setError(response.error.message);
      return;
    }
    setEntries(Array.isArray(response.payload.entries) ? response.payload.entries as PromptTagEntry[] : []);
    setError("");
  }, []);

  useEffect(() => {
    if (!open || !bridgeReady) return;
    void loadEntries();
  }, [bridgeReady, loadEntries, open]);

  async function saveEntry(): Promise<void> {
    const payload = {
      ...draft,
      id: draft.id.trim(),
      name: draft.name.trim(),
      category: draft.category.trim(),
    };
    if (!payload.id || !payload.name || !payload.category || !payload.match_terms.length || !payload.positive_tags.length) {
      setError("ID、名称、分类、匹配词和正向 tag 不能为空");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const response = await window.miraDesktop.invoke({
        method: "novelai.prompt_tags.upsert",
        payload,
      });
      if (response.error) {
        setError(response.error.message);
        return;
      }
      setDraft(emptyDraft);
      await loadEntries();
    } finally {
      setSaving(false);
    }
  }

  async function deleteEntry(id: string): Promise<void> {
    const response = await window.miraDesktop.invoke({
      method: "novelai.prompt_tags.delete",
      payload: { id },
    });
    if (response.error) {
      setError(response.error.message);
      return;
    }
    await loadEntries();
  }

  return (
    <section className="mt-3 rounded-md border border-[#D8DEE8] bg-white/85 p-3" data-testid="prompt-tag-library">
      <button
        className="flex w-full items-center justify-between text-left text-sm font-medium text-[#374151]"
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
      >
        <span>提示词库</span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open ? (
        <div className="mt-3 grid gap-2">
          <select className="rounded-md border border-[#D8DFE7] bg-white px-2 py-1.5 text-xs" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
            <option value="">全部分类</option>
            {categories.map((category) => <option key={category} value={category}>{category}</option>)}
          </select>
          {visibleEntries.map((entry) => (
            <div className="flex items-center justify-between gap-2 rounded-md border border-[#E4EAF0] px-2 py-1.5 text-xs" key={entry.id}>
              <button className="min-w-0 truncate text-left text-[#374151]" type="button" onClick={() => setDraft(entry)}>{entry.name}</button>
              <button className="shrink-0 text-[#A33]" type="button" onClick={() => void deleteEntry(entry.id)}>删除</button>
            </div>
          ))}
          <PromptTagEntryEditor
            draft={draft}
            error={error}
            saving={saving}
            bridgeReady={bridgeReady}
            onChange={setDraft}
            onSave={() => void saveEntry()}
          />
        </div>
      ) : null}
    </section>
  );
}
