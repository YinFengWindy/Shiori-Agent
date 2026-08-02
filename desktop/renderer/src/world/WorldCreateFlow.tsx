import { ArrowLeft, ArrowRight, Check, Sparkle, UserCircle } from "@phosphor-icons/react";
import { useState } from "react";
import { cx, ghostButtonClass, inputClass, primaryButtonClass } from "../shared/styles";
import type { WorldCreationInput, WorldRoleChoice } from "./types";
import { createInitialWorldCreationInput, creationSteps, isCreationStepComplete, type CreationStep } from "./worldCreationWizard";

type WorldCreateFlowProps = {
  roles: WorldRoleChoice[];
  initialSeed: string;
  busy?: boolean;
  error?: string;
  onBack: () => void;
  onCreate: (input: WorldCreationInput) => void;
};

const stepLabels: Record<CreationStep, string> = { role: "选择角色", setting: "开场设定", player: "玩家资料", review: "确认开始" };

/** Renders a focused, four-step Story creation flow. */
export function WorldCreateFlow({ roles, initialSeed, busy = false, error = "", onBack, onCreate }: WorldCreateFlowProps) {
  const [input, setInput] = useState(() => createInitialWorldCreationInput(initialSeed));
  const [stepIndex, setStepIndex] = useState(0);
  const step = creationSteps[stepIndex];
  const selectedRole = roles.find((role) => role.id === input.selectedRoleIds[0]);
  const stepComplete = isCreationStepComplete(step, input);
  const updateOc = (field: keyof WorldCreationInput["firstOc"], value: string) => setInput((current) => ({ ...current, firstOc: { ...current.firstOc, [field]: value } }));
  const next = () => setStepIndex((current) => Math.min(current + 1, creationSteps.length - 1));
  const previous = () => setStepIndex((current) => Math.max(current - 1, 0));

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden bg-[#F8F8F6]" data-testid="world-create-flow">
      <header className="border-b border-[#DFE5EA] px-5 py-4 sm:px-8">
        <div className="mx-auto flex max-w-4xl items-center gap-4"><button className="grid h-9 w-9 place-items-center rounded-md text-[#59615C] hover:bg-white" type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}><ArrowLeft /></button><div className="min-w-0 flex-1"><h1 className="m-0 font-serif text-lg font-semibold">新剧情</h1><ol className="mt-2 grid grid-cols-4 gap-2 p-0" aria-label="创建步骤">{creationSteps.map((item, index) => <li key={item} className={cx("list-none border-t pt-2 text-xs", index <= stepIndex ? "border-[#C67452] text-[#9E573E]" : "border-[#D8DDE0] text-[#7C858B]")}>{index + 1}. {stepLabels[item]}</li>)}</ol></div></div>
      </header>
      <main className="min-h-0 flex-1 overflow-y-auto px-5 py-8 sm:px-8">
        <div className="mx-auto grid max-w-2xl gap-6">
          <div><p className="m-0 text-xs text-[#7C858B]">步骤 {stepIndex + 1}/4</p><h2 className="mt-1 font-serif text-2xl font-semibold text-[#2E3438]">{stepLabels[step]}</h2></div>
          {step === "role" ? <section className="grid gap-3">{roles.map((role) => { const selected = role.id === input.selectedRoleIds[0]; return <button key={role.id} className={cx("flex min-h-20 items-center gap-3 rounded-md border p-4 text-left transition", selected ? "border-[#D88A64] bg-[#FFF7F1]" : "border-[#DDE2E5] bg-white hover:border-[#C7CDD1]")} type="button" aria-pressed={selected} onClick={() => setInput((current) => ({ ...current, selectedRoleIds: [role.id] }))}>{role.avatarUrl ? <img className="h-10 w-10 rounded-md object-cover" src={role.avatarUrl} alt="" /> : <UserCircle className="h-10 w-10 text-[#6C747A]" weight="thin" />}<span className="min-w-0 flex-1"><strong className="block text-sm">{role.name}</strong><span className="block truncate text-xs text-[#737A7F]">{role.description}</span></span>{selected ? <Check className="text-[#A75F41]" weight="bold" /> : null}</button>; })}</section> : null}
          {step === "setting" ? <section className="grid gap-4"><label className="grid gap-1.5 text-xs text-[#687078]">剧情名称<input className={inputClass} value={input.name} onChange={(event) => setInput((current) => ({ ...current, name: event.target.value }))} /></label><label className="grid gap-1.5 text-xs text-[#687078]">开场背景<textarea className={cx(inputClass, "min-h-32 resize-y")} value={input.premise} onChange={(event) => setInput((current) => ({ ...current, premise: event.target.value }))} /></label><label className="grid gap-1.5 text-xs text-[#687078]">开始时间（北京时间）<input className={inputClass} type="datetime-local" value={input.firstOc.entryTime} onChange={(event) => updateOc("entryTime", event.target.value)} /></label></section> : null}
          {step === "player" ? <section className="grid gap-4"><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-1.5 text-xs text-[#687078]">名称<input className={inputClass} value={input.firstOc.name} onChange={(event) => updateOc("name", event.target.value)} /></label><label className="grid gap-1.5 text-xs text-[#687078]">身份<input className={inputClass} value={input.firstOc.identity} onChange={(event) => updateOc("identity", event.target.value)} /></label></div><label className="grid gap-1.5 text-xs text-[#687078]">外貌<input className={inputClass} value={input.firstOc.entryLocation} onChange={(event) => updateOc("entryLocation", event.target.value)} /></label></section> : null}
          {step === "review" ? <section className="divide-y divide-[#E0E4E1] border-y border-[#E0E4E1]"><div className="grid gap-1 py-4"><span className="text-xs text-[#7C858B]">角色</span><strong>{selectedRole?.name || "未选择"}</strong></div><div className="grid gap-1 py-4"><span className="text-xs text-[#7C858B]">剧情</span><strong>{input.name}</strong><span className="text-sm text-[#5F686E]">{input.premise}</span></div><div className="grid gap-1 py-4"><span className="text-xs text-[#7C858B]">玩家</span><strong>{input.firstOc.name}，{input.firstOc.identity}</strong><span className="text-sm text-[#5F686E]">{input.firstOc.entryLocation} · {input.firstOc.entryTime}</span></div></section> : null}
          {error ? <div className="rounded-md border border-[#C77A65] bg-[#FFF3F0] px-3 py-2 text-sm text-[#9A4635]" role="alert">{error}</div> : null}
        </div>
      </main>
      <footer className="border-t border-[#DFE5EA] px-5 py-4 sm:px-8"><div className="mx-auto flex max-w-2xl justify-between gap-3">{stepIndex ? <button className={ghostButtonClass} type="button" disabled={busy} onClick={previous}>上一步</button> : <span />}{step === "review" ? <button className={primaryButtonClass} type="button" disabled={busy || !stepComplete} onClick={() => onCreate(input)}><span className="inline-flex items-center gap-2"><Sparkle weight="fill" />开始剧情</span></button> : <button className={primaryButtonClass} type="button" disabled={!stepComplete} onClick={next}><span className="inline-flex items-center gap-2">下一步<ArrowRight /></span></button>}</div></footer>
    </section>
  );
}
