import { useCallback, useEffect, useMemo, useState } from "react";
import { PromptTagEntryEditor, type PromptTagDraft } from "./PromptTagEntryEditor";
import type { PromptTagEntry } from "./types";
import { DeleteIcon } from "../shared/icons";
import { PromptLibraryIcon } from "../shared/icons";
import { toFileUrl } from "../shared/format";
import type { PromptTagWorkspaceSectionId } from "./PromptTagWorkspaceSidebar";

type PromptTagLibraryPanelProps = {
  bridgeReady: boolean;
  section: PromptTagWorkspaceSectionId;
  onOpenSection: (section: PromptTagWorkspaceSectionId) => void;
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
export function PromptTagLibraryPanel({ bridgeReady, section, onOpenSection }: PromptTagLibraryPanelProps) {
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

  useEffect(() => {
    if (section !== "create") return;
    setDraft(emptyDraft);
    setSelectedId("");
    setIsCreating(true);
    setError("");
  }, [section]);

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
      onOpenSection("detail");
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
      onOpenSection("list");
    }
    await loadEntries();
  }

  return (
    <section className="scrollbar-soft h-full overflow-y-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(247,250,253,0.98)_100%)] p-8" data-testid="prompt-tag-library">
      {section === "list" ? <div className="mx-auto w-full max-w-[1120px]"><div className="mb-5 flex justify-end gap-2"><input className="rounded-md border border-[#D8DFE7] px-3 py-2 text-xs outline-none focus:border-[#9AA3B2]" placeholder="搜索" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /><select className="rounded-md border border-[#D8DFE7] bg-white px-2 text-xs outline-none" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}><option value="">全部分类</option>{categories.map((category) => <option key={category}>{category}</option>)}</select></div><div className="grid grid-cols-3 gap-5">{visibleEntries.map((entry) => <div className="group relative h-[420px] overflow-hidden rounded-[22px] border border-[#D9E0E8] bg-[#EEF1F5] shadow-[0_14px_40px_rgba(31,41,55,0.06)] transition hover:-translate-y-0.5 hover:shadow-[0_18px_44px_rgba(31,41,55,0.1)]" key={entry.id}><button className="h-full w-full" type="button" title={entry.name} onClick={() => { setDraft(entry); setSelectedId(entry.id); setIsCreating(false); setError(""); onOpenSection("detail"); }}>{entry.image_path ? <img className="h-full w-full object-cover" src={toFileUrl(entry.image_path)} alt={entry.name} /> : <span className="grid h-full place-items-center text-[#9AA3B2]"><PromptLibraryIcon className="h-12 w-12 fill-current" /></span>}</button><button className="absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-full border border-white/24 bg-[rgba(15,23,42,0.62)] text-white opacity-0 transition hover:bg-[rgba(143,43,24,0.88)] group-hover:opacity-100" type="button" aria-label={`删除 ${entry.name}`} onClick={() => void deleteEntry(entry.id)}><DeleteIcon className="h-[15px] w-[15px] fill-current" /></button></div>)}</div></div> : <div className="mx-auto w-full max-w-[1120px]"><PromptTagEntryEditor draft={draft} error={error} saving={saving} bridgeReady={bridgeReady} isCreating={section === "create" || isCreating} onChange={setDraft} onSave={() => void saveEntry()} onBack={() => onOpenSection("list")} onReset={() => setDraft(selectedId ? entries.find((entry) => entry.id === selectedId) ?? emptyDraft : emptyDraft)} /></div>}
    </section>
  );
}
