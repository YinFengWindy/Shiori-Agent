import { useCallback, useEffect, useMemo, useState } from "react";
import { PromptTagEntryEditor, type PromptTagDraft } from "./PromptTagEntryEditor";
import type { PromptTagEntry } from "./types";
import { BackIcon, DeleteIcon, PlusIcon } from "../shared/icons";
import { PromptLibraryIcon } from "../shared/icons";
import { toFileUrl } from "../shared/format";

type PromptTagLibraryPanelProps = {
  bridgeReady: boolean;
  onBackToApp: () => void;
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
  image_path: "",
};

/** Manages the editable prompt-tag catalog on its dedicated page. */
export function PromptTagLibraryPanel({ bridgeReady, onBackToApp }: PromptTagLibraryPanelProps) {
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
      setIsCreating(false);
    }
    await loadEntries();
  }

  return (
    <section className="grid h-full min-h-0 grid-cols-[280px_minmax(0,1fr)] bg-white" data-testid="prompt-tag-library">
      <aside className="flex min-h-0 flex-col border-r border-[#E5EAF0] bg-[#EFF4F9] px-[18px] py-[18px]">
        <button className="mb-5 flex min-h-[38px] items-center gap-2.5 rounded-[10px] px-2 text-[13px] text-[#3F3F3F] transition hover:bg-[#E2E8EF]" type="button" onClick={onBackToApp}><BackIcon className="h-4 w-4 fill-current" /><span>返回应用</span></button>
        <div className="grid gap-1.5">
          <button className="grid min-h-[42px] grid-cols-[20px_1fr] items-center gap-2.5 rounded-[10px] bg-white/70 px-3 text-left text-sm text-[#272536] shadow-[0_6px_18px_rgba(15,23,42,0.06)]" type="button" onClick={() => { setSelectedId(""); setIsCreating(false); setError(""); }}><PromptLibraryIcon className="h-4 w-4 fill-current" /><span>提示词列表</span></button>
          <button className="grid min-h-[42px] grid-cols-[20px_1fr] items-center gap-2.5 rounded-[10px] px-3 text-left text-sm text-[#272536] transition hover:bg-[#E2E8EF]" type="button" onClick={() => { setDraft(emptyDraft); setSelectedId(""); setIsCreating(true); setError(""); }}><PlusIcon className="h-4 w-4 fill-current" /><span>新建提示词</span></button>
        </div>
      </aside>
      <main className="scrollbar-soft min-w-0 overflow-y-auto bg-white p-8">
        {selectedId || isCreating ? <PromptTagEntryEditor draft={draft} error={error} saving={saving} bridgeReady={bridgeReady} isCreating={isCreating} onChange={setDraft} onSave={() => void saveEntry()} /> : <div><div className="mb-5 flex items-center justify-between gap-3"><div><h1 className="text-xl font-semibold text-[#263241]">提示词列表</h1><p className="mt-1 text-xs text-[#7B8490]">{entries.length} 个素材</p></div><div className="flex gap-2"><input className="rounded-md border border-[#D8DFE7] px-3 py-2 text-xs outline-none focus:border-[#9AA3B2]" placeholder="搜索" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /><select className="rounded-md border border-[#D8DFE7] bg-white px-2 text-xs outline-none" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}><option value="">全部分类</option>{categories.map((category) => <option key={category}>{category}</option>)}</select></div></div><div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-4">{visibleEntries.map((entry) => <div className="group relative aspect-square overflow-hidden rounded-[18px] border border-[#D8DFE7] bg-[#F5F7FA] transition hover:border-[#9AA3B2]" key={entry.id}><button className="h-full w-full" type="button" title={entry.name} onClick={() => { setDraft(entry); setSelectedId(entry.id); setIsCreating(false); setError(""); }}>{entry.image_path ? <img className="h-full w-full object-cover" src={toFileUrl(entry.image_path)} alt={entry.name} /> : <span className="grid h-full place-items-center text-[#9AA3B2]"><PromptLibraryIcon className="h-10 w-10 fill-current" /></span>}</button><button className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-full border border-black/10 bg-white/90 text-[#64748B] opacity-0 transition hover:text-[#B33A3A] group-hover:opacity-100" type="button" aria-label={`删除 ${entry.name}`} onClick={() => void deleteEntry(entry.id)}><DeleteIcon className="h-3.5 w-3.5 fill-current" /></button></div>)}</div></div>}
      </main>
    </section>
  );
}
