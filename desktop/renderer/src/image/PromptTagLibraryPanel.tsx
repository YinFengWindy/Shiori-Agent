import { useCallback, useEffect, useMemo, useState } from "react";
import { PromptTagEntryEditor, type PromptTagDraft } from "./PromptTagEntryEditor";
import type { PromptTagEntry } from "./types";
import { DeleteIcon, PlusIcon } from "../shared/icons";

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

/** Manages the editable prompt-tag catalog on its dedicated page. */
export function PromptTagLibraryPanel({ bridgeReady }: PromptTagLibraryPanelProps) {
  const [entries, setEntries] = useState<PromptTagEntry[]>([]);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [draft, setDraft] = useState<PromptTagDraft>(emptyDraft);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const categories = useMemo(() => [...new Set(entries.map((entry) => entry.category))].sort(), [entries]);
  const visibleEntries = useMemo(() => entries.filter((entry) => {
    const query = searchQuery.trim().toLowerCase();
    const matchesQuery = !query || entry.name.toLowerCase().includes(query) || entry.id.toLowerCase().includes(query);
    return matchesQuery && (!categoryFilter || entry.category === categoryFilter);
  }), [categoryFilter, entries, searchQuery]);

  const loadEntries = useCallback(async (): Promise<void> => {
    const response = await window.miraDesktop.invoke({
      method: "novelai.prompt_tags.list",
      payload: {},
    });
    if (response.error) {
      setError(response.error.message);
      return;
    }
    const nextEntries = Array.isArray(response.payload.entries) ? response.payload.entries as PromptTagEntry[] : [];
    setEntries(nextEntries);
    if (!isCreating && selectedId) {
      const selected = nextEntries.find((entry) => entry.id === selectedId);
      if (selected) setDraft(selected);
    }
    setError("");
  }, [isCreating, selectedId]);

  useEffect(() => {
    if (!bridgeReady) return;
    void loadEntries();
  }, [bridgeReady, loadEntries]);

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
      setSelectedId(payload.id);
      setIsCreating(false);
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
    if (selectedId === id) {
      setSelectedId("");
      setDraft(emptyDraft);
      setIsCreating(true);
    }
    await loadEntries();
  }

  return (
    <section className="grid gap-4" data-testid="prompt-tag-library">
      <div className="flex items-center justify-between gap-3">
        <div><h1 className="text-lg font-semibold text-[#263241]">提示词库</h1><p className="mt-1 text-xs text-[#7B8490]">{entries.length} 个条目</p></div>
        <button className="flex items-center gap-1.5 rounded-md bg-[#2F6FED] px-3 py-2 text-xs font-medium text-white transition hover:bg-[#245BC2]" type="button" onClick={() => { setDraft(emptyDraft); setSelectedId(""); setIsCreating(true); setError(""); }}><PlusIcon className="h-3.5 w-3.5 fill-current" />新建</button>
      </div>
      <div className="grid min-h-[520px] grid-cols-[280px_minmax(0,1fr)] overflow-hidden rounded-lg border border-[#DDE4EC] bg-white shadow-[0_12px_32px_rgba(31,41,55,0.06)]">
        <aside className="border-r border-[#E5EAF0] bg-[#F8FAFC] p-3">
          <div className="grid gap-2">
            <input className="rounded-md border border-[#D8DFE7] bg-white px-3 py-2 text-xs outline-none transition focus:border-[#2F6FED]" placeholder="搜索名称或 ID" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} />
            <select className="rounded-md border border-[#D8DFE7] bg-white px-2 py-2 text-xs outline-none" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}><option value="">全部分类</option>{categories.map((category) => <option key={category} value={category}>{category}</option>)}</select>
          </div>
          <div className="mt-3 grid gap-1.5">
            {visibleEntries.map((entry) => <div className={`group flex items-center gap-2 rounded-md px-2.5 py-2 text-xs transition ${selectedId === entry.id && !isCreating ? "bg-[#E7F0FF] text-[#245BC2]" : "text-[#374151] hover:bg-white"}`} key={entry.id}><button className="min-w-0 flex-1 text-left" type="button" onClick={() => { setDraft(entry); setSelectedId(entry.id); setIsCreating(false); setError(""); }}><span className="block truncate font-medium">{entry.name || entry.id}</span><span className="mt-0.5 block truncate text-[10px] text-[#8A94A1]">{entry.category} · {entry.enabled ? "启用" : "停用"}</span></button><button className="rounded p-1 text-[#A4ACB6] opacity-0 transition hover:bg-[#FDECEC] hover:text-[#B33A3A] group-hover:opacity-100" type="button" aria-label={`删除 ${entry.name}`} onClick={() => void deleteEntry(entry.id)}><DeleteIcon className="h-3 w-3 fill-current" /></button></div>)}
            {!visibleEntries.length ? <div className="px-2 py-8 text-center text-xs text-[#8A94A1]">暂无条目</div> : null}
          </div>
        </aside>
        <div className="min-w-0 p-5"><PromptTagEntryEditor draft={draft} error={error} saving={saving} bridgeReady={bridgeReady} isCreating={isCreating} onChange={setDraft} onSave={() => void saveEntry()} /></div>
      </div>
    </section>
  );
}
