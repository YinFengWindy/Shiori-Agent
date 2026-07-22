import { ArrowLeft, Copy, GitBranch, Plus, Warning } from "@phosphor-icons/react";
import { useState } from "react";
import { cx, inputClass, primaryButtonClass } from "../shared/styles";
import type { BackfillPreview, WorldCreationInput, WorldTimelineEntry } from "./types";

type WorldTimelineViewProps = {
  worldName: string;
  activeOcName: string;
  entries: WorldTimelineEntry[];
  perspective: "known" | "omniscient";
  backfillPreview?: BackfillPreview | null;
  onBack: () => void;
  onPerspectiveChange: (value: "known" | "omniscient") => void;
  onCopyWorld: (anchorId: string) => void;
  onPreviewBackfill: (anchorId: string, oc: WorldCreationInput["firstOc"]) => void;
  onCommitBackfill: (preview: BackfillPreview) => void;
};

const blankOc: WorldCreationInput["firstOc"] = { name: "", identity: "", entryTime: "", entryLocation: "", primaryGoal: "" };

/** Renders the full-width shared history, copy, and past-entry workflow. */
export function WorldTimelineView({ worldName, activeOcName, entries, perspective, backfillPreview, onBack, onPerspectiveChange, onCopyWorld, onPreviewBackfill, onCommitBackfill }: WorldTimelineViewProps) {
  const [entryAnchor, setEntryAnchor] = useState<string | null>(null);
  const [oc, setOc] = useState(blankOc);
  const updateOc = (field: keyof typeof oc, value: string) => setOc((current) => ({ ...current, [field]: value }));
  return (
    <section className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-[#F7F7F4]" data-testid="world-timeline-view">
      <header className="flex items-center justify-between border-b border-[#E1E2DD] bg-white px-5 py-3"><div className="flex items-center gap-3"><button className="grid h-9 w-9 place-items-center rounded-md hover:bg-[#F0F2F0]" type="button" aria-label="返回当前场景" onClick={onBack}><ArrowLeft /></button><div><h1 className="m-0 font-serif text-lg font-semibold">{worldName} · 时间线</h1><p className="m-0 text-xs text-[#747A76]">{perspective === "known" ? `${activeOcName} 所知` : "完整世界"}</p></div></div><div className="inline-flex rounded-md border border-[#D9DDD9] bg-[#F2F4F2] p-1"><button className={cx("rounded-md px-3 py-1.5 text-xs", perspective === "known" && "bg-white shadow-sm")} type="button" onClick={() => onPerspectiveChange("known")}>认知</button><button className={cx("rounded-md px-3 py-1.5 text-xs", perspective === "omniscient" && "bg-white shadow-sm")} type="button" onClick={() => onPerspectiveChange("omniscient")}>全知</button></div></header>
      <div className="min-h-0 overflow-y-auto px-6 py-7"><div className="mx-auto max-w-4xl"><ol className="relative m-0 grid gap-0 border-l border-[#BBC2BC] pl-7">{entries.map((entry) => <li key={entry.id} className="relative pb-8"><span className="absolute -left-[34px] top-1 h-3 w-3 rounded-full border-2 border-[#F7F7F4] bg-[#7A857D]" /><time className="text-xs text-[#7A807C]">{entry.timeLabel}</time><div className="mt-1 rounded-md border border-[#DEE2DD] bg-white p-4"><h2 className="m-0 font-serif text-base font-semibold">{entry.title}</h2><p className="m-0 mt-2 text-sm leading-6 text-[#5D635F]">{entry.summary}</p>{entry.involvedNames.length ? <p className="m-0 mt-2 text-xs text-[#858B87]">{entry.involvedNames.join(" · ")}</p> : null}<div className="mt-3 flex gap-2">{entry.canEnter ? <button className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#DADFDA] px-2.5 text-xs" type="button" onClick={() => setEntryAnchor(entry.id)}><Plus />从这里加入 OC</button> : null}{entry.canCopy ? <button className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#DADFDA] px-2.5 text-xs" type="button" onClick={() => onCopyWorld(entry.id)}><Copy />创建世界副本</button> : null}</div></div></li>)}</ol>{entryAnchor ? <section className="ml-7 grid gap-3 rounded-md border border-[#D8DDD7] bg-white p-4"><div className="flex items-center gap-2"><GitBranch /><h2 className="m-0 font-serif text-base font-semibold">过去入场</h2></div><div className="grid grid-cols-2 gap-2"><input className={inputClass} placeholder="名字" value={oc.name} onChange={(event) => updateOc("name", event.target.value)} /><input className={inputClass} placeholder="身份描述" value={oc.identity} onChange={(event) => updateOc("identity", event.target.value)} /><input className={inputClass} type="datetime-local" value={oc.entryTime} onChange={(event) => updateOc("entryTime", event.target.value)} /><input className={inputClass} placeholder="入场地点" value={oc.entryLocation} onChange={(event) => updateOc("entryLocation", event.target.value)} /></div><input className={inputClass} placeholder="主要目标" value={oc.primaryGoal} onChange={(event) => updateOc("primaryGoal", event.target.value)} /><button className={primaryButtonClass} type="button" disabled={!oc.name || !oc.identity || !oc.entryTime || !oc.entryLocation} onClick={() => onPreviewBackfill(entryAnchor, oc)}>查看历史影响</button>{backfillPreview ? <div className={cx("rounded-md p-3 text-sm", backfillPreview.allowed ? "bg-[#EEF5EF]" : "bg-[#FFF2ED]")}>{backfillPreview.conflicts.length ? <div className="flex items-start gap-2 text-[#8A493B]"><Warning className="mt-0.5 shrink-0" />{backfillPreview.conflicts.join("；")}</div> : <div className="grid gap-2">{backfillPreview.stages.map((stage) => <div key={stage.title}><strong>{stage.title}</strong><p className="m-0 text-xs text-[#687069]">{stage.summary}</p></div>)}</div>}{backfillPreview.allowed ? <button className={cx(primaryButtonClass, "mt-3")} type="button" onClick={() => onCommitBackfill(backfillPreview)}>确认加入世界</button> : null}</div> : null}</section> : null}</div></div>
    </section>
  );
}
