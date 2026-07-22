import { Check, Copy, DiceFive, Sparkle, UserCircle } from "@phosphor-icons/react";
import { useState } from "react";
import { cx, inputClass, primaryButtonClass } from "../shared/styles";
import type { NativeIdentityDraft, WorldCreationDraft, WorldCreationInput, WorldRoleChoice } from "./types";

type WorldCreateFlowProps = {
  roles: WorldRoleChoice[];
  initialSeed: string;
  busy?: boolean;
  draft?: WorldCreationDraft | null;
  onRerollSeed: () => string;
  onPreview: (input: WorldCreationInput) => void;
  onConfirm: (draftId: string, identities: NativeIdentityDraft[]) => void;
};

function initialInput(seed: string): WorldCreationInput {
  return { name: "", premise: "", rules: "", tone: "", selectedRoleIds: [], seed, firstOc: { name: "", identity: "", entryTime: "", entryLocation: "", primaryGoal: "" } };
}

/** Renders semantic world creation, native-identity review, and first-OC entry. */
export function WorldCreateFlow({ roles, initialSeed, busy = false, draft, onRerollSeed, onPreview, onConfirm }: WorldCreateFlowProps) {
  const [input, setInput] = useState(() => initialInput(initialSeed));
  const [identities, setIdentities] = useState<NativeIdentityDraft[] | null>(null);
  const reviewed = identities ?? draft?.nativeIdentities ?? [];
  const canPreview = Boolean(input.name.trim() && input.premise.trim() && input.firstOc.name.trim() && input.firstOc.identity.trim() && input.firstOc.entryTime.trim() && input.firstOc.entryLocation.trim());
  const updateOc = (field: keyof WorldCreationInput["firstOc"], value: string) => setInput((current) => ({ ...current, firstOc: { ...current.firstOc, [field]: value } }));
  const updateIdentity = (index: number, field: keyof NativeIdentityDraft, value: string | boolean) => setIdentities(reviewed.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item));

  return (
    <section className="grid h-full min-h-0 grid-cols-[220px_minmax(420px,1fr)_300px] overflow-hidden bg-[#F8F8F6]" data-testid="world-create-flow">
      <aside className="border-r border-[#DFE5EA] bg-[#EFF4F9] p-4"><h1 className="m-0 font-serif text-lg font-semibold">新世界</h1><ol className="mt-5 grid gap-3 p-0 text-sm text-[#626B71]"><li className="list-none text-[#A75F41]">01 世界轮廓</li><li className="list-none">02 原住民</li><li className="list-none">03 首位 OC</li></ol></aside>
      <main className="min-h-0 overflow-y-auto px-8 py-7">
        <div className="mx-auto grid max-w-2xl gap-8">
          <section className="grid gap-4"><h2 className="m-0 font-serif text-xl font-semibold">世界轮廓</h2><label className="grid gap-1.5 text-xs text-[#687078]">世界名称<input className={inputClass} value={input.name} onChange={(event) => setInput({ ...input, name: event.target.value })} /></label><label className="grid gap-1.5 text-xs text-[#687078]">核心前提<textarea className={cx(inputClass, "min-h-24 resize-none")} value={input.premise} onChange={(event) => setInput({ ...input, premise: event.target.value })} /></label><div className="grid grid-cols-2 gap-3"><label className="grid gap-1.5 text-xs text-[#687078]">演化规则<input className={inputClass} value={input.rules} onChange={(event) => setInput({ ...input, rules: event.target.value })} /></label><label className="grid gap-1.5 text-xs text-[#687078]">叙事基调<input className={inputClass} value={input.tone} onChange={(event) => setInput({ ...input, tone: event.target.value })} /></label></div></section>
          <section className="grid gap-3"><h2 className="m-0 font-serif text-xl font-semibold">选择原住民</h2><div className="grid grid-cols-2 gap-2">{roles.map((role) => { const selected = input.selectedRoleIds.includes(role.id); return <button key={role.id} className={cx("flex min-h-16 items-center gap-3 rounded-md border p-3 text-left", selected ? "border-[#D88A64] bg-[#FFF7F1]" : "border-[#DDE2E5] bg-white")} type="button" aria-pressed={selected} onClick={() => setInput((current) => ({ ...current, selectedRoleIds: selected ? current.selectedRoleIds.filter((id) => id !== role.id) : [...current.selectedRoleIds, role.id] }))}>{role.avatarUrl ? <img className="h-9 w-9 rounded-md object-cover" src={role.avatarUrl} alt="" /> : <UserCircle className="h-9 w-9" weight="thin" />}<span><strong className="block text-sm">{role.name}</strong><span className="line-clamp-1 text-xs text-[#737A7F]">{role.description}</span></span>{selected ? <Check className="ml-auto" /> : null}</button>; })}</div></section>
          <section className="grid gap-4"><h2 className="m-0 font-serif text-xl font-semibold">首位 OC</h2><div className="grid grid-cols-2 gap-3"><label className="grid gap-1.5 text-xs text-[#687078]">名字<input className={inputClass} value={input.firstOc.name} onChange={(event) => updateOc("name", event.target.value)} /></label><label className="grid gap-1.5 text-xs text-[#687078]">身份描述<input className={inputClass} value={input.firstOc.identity} onChange={(event) => updateOc("identity", event.target.value)} /></label><label className="grid gap-1.5 text-xs text-[#687078]">入场时间<input className={inputClass} type="datetime-local" value={input.firstOc.entryTime} onChange={(event) => updateOc("entryTime", event.target.value)} /></label><label className="grid gap-1.5 text-xs text-[#687078]">入场地点<input className={inputClass} value={input.firstOc.entryLocation} onChange={(event) => updateOc("entryLocation", event.target.value)} /></label></div><label className="grid gap-1.5 text-xs text-[#687078]">最初目标<input className={inputClass} value={input.firstOc.primaryGoal} onChange={(event) => updateOc("primaryGoal", event.target.value)} /></label></section>
          <section className="flex items-center justify-between rounded-md border border-[#DDE2E5] bg-white p-3"><div><span className="block text-xs text-[#737A7F]">世界种子</span><code className="text-sm text-[#353A3D]">{input.seed}</code></div><div className="flex gap-1"><button className="grid h-8 w-8 place-items-center rounded-md hover:bg-[#F1F3F4]" type="button" aria-label="复制世界种子" onClick={() => void navigator.clipboard?.writeText(input.seed)}><Copy /></button><button className="grid h-8 w-8 place-items-center rounded-md hover:bg-[#F1F3F4]" type="button" aria-label="换一个种子" onClick={() => setInput({ ...input, seed: onRerollSeed() })}><DiceFive /></button></div></section>
          <button className={primaryButtonClass} type="button" disabled={busy || !canPreview} onClick={() => onPreview(input)}><span className="inline-flex items-center gap-2"><Sparkle weight="fill" />生成原住民草案</span></button>
        </div>
      </main>
      <aside className="min-h-0 overflow-y-auto border-l border-[#E0E4E1] bg-white p-4"><h2 className="m-0 font-serif text-base font-semibold">原住民草案</h2>{reviewed.length ? <div className="mt-4 grid gap-4">{reviewed.map((item, index) => <section key={item.roleId} className="grid gap-2 rounded-md border border-[#E2E4DF] bg-[#FAFAF8] p-3"><div className="flex items-center justify-between"><strong className="text-sm">{item.roleName}</strong><label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={item.accepted} onChange={(event) => updateIdentity(index, "accepted", event.target.checked)} />接受</label></div><input className={cx(inputClass, "py-2")} value={item.nativeName} aria-label={`${item.roleName} 在地姓名`} onChange={(event) => updateIdentity(index, "nativeName", event.target.value)} /><textarea className={cx(inputClass, "min-h-20 resize-none py-2 text-xs")} value={item.identity} aria-label={`${item.roleName} 在地身份`} onChange={(event) => updateIdentity(index, "identity", event.target.value)} /><textarea className={cx(inputClass, "min-h-20 resize-none py-2 text-xs")} value={item.history} aria-label={`${item.roleName} 在地经历`} onChange={(event) => updateIdentity(index, "history", event.target.value)} /></section>)}<button className={primaryButtonClass} type="button" disabled={busy || !draft || reviewed.some((item) => !item.accepted)} onClick={() => draft && onConfirm(draft.id, reviewed)}>确认世界与 OC</button></div> : null}</aside>
    </section>
  );
}
