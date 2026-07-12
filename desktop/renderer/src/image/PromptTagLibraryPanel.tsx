import { useCallback, useEffect, useState } from "react";
import { toFileUrl } from "../shared/format";
import { DeleteIcon, PromptLibraryIcon } from "../shared/icons";
import { PromptTagEntryEditor, type PromptTagDraft } from "./PromptTagEntryEditor";
import type { PromptTagWorkspaceSectionId } from "./PromptTagWorkspaceSidebar";
import type { PromptTagEntry } from "./types";

type PromptTagLibraryPanelProps = { bridgeReady: boolean; section: PromptTagWorkspaceSectionId; onOpenSection: (section: PromptTagWorkspaceSectionId) => void };
const emptyDraft: PromptTagDraft = { id: "", name: "", enabled: true, category: "composition", match_terms: [], positive_tags: [], negative_tags: [], rating: "general", image_path: "" };
function draftSignature(draft: PromptTagDraft): string { return JSON.stringify({ id: draft.id.trim(), name: draft.name.trim(), enabled: draft.enabled, category: draft.category.trim(), match_terms: draft.match_terms, positive_tags: draft.positive_tags, negative_tags: draft.negative_tags, rating: draft.rating, image_path: draft.image_path }); }

/** Manages prompt-tag workspace data and routes between its list and editor views. */
export function PromptTagLibraryPanel({ bridgeReady, section, onOpenSection }: PromptTagLibraryPanelProps) {
  const [entries, setEntries] = useState<PromptTagEntry[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [draft, setDraft] = useState<PromptTagDraft>(emptyDraft);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const loadEntries = useCallback(async (): Promise<void> => { const response = await window.miraDesktop.invoke({ method: "novelai.prompt_tags.list", payload: {} }); if (response.error) { setError(response.error.message); return; } const nextEntries = Array.isArray(response.payload.entries) ? response.payload.entries as PromptTagEntry[] : []; setEntries(nextEntries); if (!isCreating && selectedId) { const selected = nextEntries.find((entry) => entry.id === selectedId); if (selected) setDraft(selected); } setError(""); }, [isCreating, selectedId]);
  useEffect(() => { if (bridgeReady) void loadEntries(); }, [bridgeReady, loadEntries]);
  useEffect(() => { if (section !== "create") return; setDraft(emptyDraft); setSelectedId(""); setIsCreating(true); setError(""); }, [section]);
  const originalDraft = selectedId ? entries.find((entry) => entry.id === selectedId) ?? emptyDraft : emptyDraft;
  const dirty = draftSignature(draft) !== draftSignature(originalDraft);
  async function saveEntry(): Promise<void> { const payload = { ...draft, id: draft.id.trim(), name: draft.name.trim(), category: draft.category.trim() }; if (!payload.id || !payload.name || !payload.category || !payload.match_terms.length || !payload.positive_tags.length) { setError("ID、名称、分类、匹配词和正向 tag 不能为空"); return; } setSaving(true); setError(""); try { const response = await window.miraDesktop.invoke({ method: "novelai.prompt_tags.upsert", payload }); if (response.error) { setError(response.error.message); return; } setSelectedId(payload.id); setIsCreating(false); onOpenSection("detail"); await loadEntries(); } finally { setSaving(false); } }
  async function deleteEntry(id: string): Promise<void> { const response = await window.miraDesktop.invoke({ method: "novelai.prompt_tags.delete", payload: { id } }); if (response.error) { setError(response.error.message); return; } if (selectedId === id) { setSelectedId(""); setDraft(emptyDraft); setIsCreating(false); onOpenSection("list"); } await loadEntries(); }
  function openEntry(entry: PromptTagEntry): void { setDraft(entry); setSelectedId(entry.id); setIsCreating(false); setError(""); onOpenSection("detail"); }
  return <section className="scrollbar-soft h-full overflow-y-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(247,250,253,0.98)_100%)] p-8" data-testid="prompt-tag-library">{section === "list" ? <div className="mx-auto grid w-full max-w-[1120px] grid-cols-3 gap-5">{entries.map((entry) => <div className="group relative h-[420px] overflow-hidden rounded-[22px] border border-[#D9E0E8] bg-[#EEF1F5] shadow-[0_14px_40px_rgba(31,41,55,0.06)] transition hover:-translate-y-0.5 hover:shadow-[0_18px_44px_rgba(31,41,55,0.1)]" key={entry.id}><button className="h-full w-full" type="button" title={entry.name} onClick={() => openEntry(entry)}>{entry.image_path ? <img className="h-full w-full object-cover" src={toFileUrl(entry.image_path)} alt={entry.name} /> : <span className="grid h-full place-items-center text-[#9AA3B2]"><PromptLibraryIcon className="h-12 w-12 fill-current" /></span>}</button><div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 via-black/25 to-transparent px-5 pb-5 pt-14 text-white"><div className="truncate text-lg font-semibold">{entry.name}</div><div className="mt-1 truncate text-xs text-white/75">{entry.category}</div></div><button className="absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-full border border-white/24 bg-[rgba(15,23,42,0.62)] text-white opacity-0 transition hover:bg-[rgba(143,43,24,0.88)] group-hover:opacity-100" type="button" aria-label={`删除 ${entry.name}`} onClick={() => void deleteEntry(entry.id)}><DeleteIcon className="h-[15px] w-[15px] fill-current" /></button></div>)}</div> : <div className="mx-auto w-full max-w-[1120px]"><PromptTagEntryEditor draft={draft} error={error} saving={saving} bridgeReady={bridgeReady} dirty={dirty} isCreating={section === "create" || isCreating} onChange={setDraft} onSave={() => void saveEntry()} onBack={() => onOpenSection("list")} onReset={() => setDraft(selectedId ? entries.find((entry) => entry.id === selectedId) ?? emptyDraft : emptyDraft)} /></div>}</section>;
}
