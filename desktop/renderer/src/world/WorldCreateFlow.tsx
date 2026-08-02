import { ArrowLeft, Check, Sparkle, UserCircle } from "@phosphor-icons/react";
import { useState } from "react";
import { cx, inputClass, primaryButtonClass } from "../shared/styles";
import type { NativeIdentityDraft, WorldCreationDraft, WorldCreationInput, WorldRoleChoice } from "./types";

type WorldCreateFlowProps = {
  roles: WorldRoleChoice[];
  initialSeed: string;
  busy?: boolean;
  draft?: WorldCreationDraft | null;
  onBack: () => void;
  onRerollSeed: () => string;
  onPreview: (input: WorldCreationInput) => void;
  onConfirm: (draftId: string, identities: NativeIdentityDraft[]) => void;
};

function initialInput(seed: string): WorldCreationInput {
  return { name: "", premise: "", rules: "", tone: "", selectedRoleIds: [], seed, firstOc: { name: "", identity: "", entryTime: "", entryLocation: "", primaryGoal: "" } };
}

/** Renders Story creation while retaining the existing three-column layout. */
export function WorldCreateFlow({ roles, initialSeed, busy = false, draft, onBack, onRerollSeed, onPreview, onConfirm }: WorldCreateFlowProps) {
  const [input, setInput] = useState(() => initialInput(initialSeed));
  const reviewed = draft?.nativeIdentities ?? [];
  const canPreview = Boolean(input.name.trim() && input.premise.trim() && input.selectedRoleIds.length === 1 && input.firstOc.name.trim() && input.firstOc.identity.trim() && input.firstOc.entryTime.trim() && input.firstOc.entryLocation.trim());
  const updateOc = (field: keyof WorldCreationInput["firstOc"], value: string) => setInput((current) => ({ ...current, firstOc: { ...current.firstOc, [field]: value } }));

  return (
    <section className="grid h-full min-h-0 grid-cols-[220px_minmax(420px,1fr)_300px] overflow-hidden bg-[#F8F8F6]" data-testid="world-create-flow">
      <aside className="border-r border-[#DFE5EA] bg-[#EFF4F9] p-4"><div className="flex items-center gap-2"><button className="grid h-9 w-9 place-items-center rounded-md text-[#59615C] hover:bg-white" type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}><ArrowLeft /></button><h1 className="m-0 font-serif text-lg font-semibold">新剧情</h1></div><ol className="mt-5 grid gap-3 p-0 text-sm text-[#626B71]"><li className="list-none text-[#A75F41]">01 开场设定</li><li className="list-none">02 选择角色</li><li className="list-none">03 玩家资料</li></ol></aside>
      <main className="min-h-0 overflow-y-auto px-8 py-7">
        <div className="mx-auto grid max-w-2xl gap-8">
          <section className="grid gap-4"><h2 className="m-0 font-serif text-xl font-semibold">开场设定</h2><label className="grid gap-1.5 text-xs text-[#687078]">剧情名称<input className={inputClass} value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} /></label><label className="grid gap-1.5 text-xs text-[#687078]">开场背景<textarea className={cx(inputClass, "min-h-24 resize-none")} value={input.premise} onChange={(event) => setInput({ ...input, premise: event.target.value })} /></label></section>
          <section className="grid gap-3"><h2 className="m-0 font-serif text-xl font-semibold">选择角色</h2><div className="grid grid-cols-2 gap-2">{roles.map((role) => { const selected = input.selectedRoleIds.includes(role.id); return <button key={role.id} className={cx("flex min-h-16 items-center gap-3 rounded-md border p-3 text-left", selected ? "border-[#D88A64] bg-[#FFF7F1]" : "border-[#DDE2E5] bg-white")} type="button" aria-pressed={selected} onClick={() => setInput((current) => ({ ...current, selectedRoleIds: selected ? [] : [role.id] }))}>{role.avatarUrl ? <img className="h-9 w-9 rounded-md object-cover" src={role.avatarUrl} alt="" /> : <UserCircle className="h-9 w-9" weight="thin" />}<span><strong className="block text-sm">{role.name}</strong><span className="line-clamp-1 text-xs text-[#737A7F]">{role.description}</span></span>{selected ? <Check className="ml-auto" /> : null}</button>; })}</div></section>
          <section className="grid gap-4"><h2 className="m-0 font-serif text-xl font-semibold">玩家资料</h2><div className="grid grid-cols-2 gap-3"><label className="grid gap-1.5 text-xs text-[#687078]">名称<input className={inputClass} value={input.firstOc.name} onChange={(event) => updateOc("name", event.target.value)} /></label><label className="grid gap-1.5 text-xs text-[#687078]">身份<input className={inputClass} value={input.firstOc.identity} onChange={(event) => updateOc("identity", event.target.value)} /></label><label className="grid gap-1.5 text-xs text-[#687078]">开始时间<input className={inputClass} type="datetime-local" value={input.firstOc.entryTime} onChange={(event) => updateOc("entryTime", event.target.value)} /></label><label className="grid gap-1.5 text-xs text-[#687078]">外貌<input className={inputClass} value={input.firstOc.entryLocation} onChange={(event) => updateOc("entryLocation", event.target.value)} /></label></div></section>
          <button className={primaryButtonClass} type="button" disabled={busy || !canPreview} onClick={() => onPreview(input)}><span className="inline-flex items-center gap-2"><Sparkle weight="fill" />确认并开始</span></button>
        </div>
      </main>
      <aside className="min-h-0 overflow-y-auto border-l border-[#E0E4E1] bg-white p-4"><h2 className="m-0 font-serif text-base font-semibold">开始剧情</h2><p className="mt-3 text-sm leading-6 text-[#687078]">角色和玩家资料会在开场时固定下来。</p>{reviewed.length ? <div className="mt-4 grid gap-4"><button className={primaryButtonClass} type="button" disabled={busy || !draft} onClick={() => draft && onConfirm(draft.id, reviewed)}>开始</button></div> : null}</aside>
    </section>
  );
}
