import { ArrowLeft, ArrowRight, Check, Sparkle, UserCircle } from "@phosphor-icons/react";
import { useState } from "react";
import { cx, ghostButtonClass, inputClass } from "../shared/styles";
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

const stepLabels: Record<CreationStep, string> = {
  role: "选择角色",
  setting: "开场设定",
  player: "玩家资料",
  review: "确认开始",
};
const romanceInputClass = cx(inputClass, "border-[#E5B8C9] !bg-white/85 text-[#4A2738] focus:!border-[#BF5C83] focus:ring-2 focus:ring-[#EFC7D7]/55");
const romancePrimaryButtonClass = "inline-flex items-center justify-center rounded-md border border-[#A93E6A] bg-[#A93E6A] px-[18px] py-3 text-white transition-colors hover:bg-[#902B57] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0] disabled:cursor-default disabled:opacity-50";

/** Renders a romance visual-novel themed, four-step Story creation flow. */
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
    <section className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[#FFF8FC] text-[#4A2738]" data-testid="world-create-flow">
      <div aria-hidden="true" className="pointer-events-none absolute inset-[clamp(12px,2vw,28px)] border border-[#E9C4D5]/70" />
      <header className="relative z-10 border-b border-[#E9C4D5] bg-white/60 px-5 py-4 sm:px-8">
        <div className="mx-auto flex max-w-4xl items-center gap-4">
          <button className="grid h-9 w-9 place-items-center rounded-md border border-[#D89AB4]/55 bg-white/65 text-[#8F355C] transition-colors hover:border-[#B64B75] hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]" type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}><ArrowLeft /></button>
          <div className="min-w-0 flex-1">
            <p className="m-0 font-serif text-sm italic text-[#B64B75] [text-shadow:0_1px_0_rgba(255,255,255,0.9)]">CREATE A STORY</p>
            <h1 className="m-0 mt-0.5 font-serif text-xl font-semibold text-[#5E2841]">新剧情</h1>
            <ol className="mt-3 grid grid-cols-4 gap-2 p-0" aria-label="创建步骤">
              {creationSteps.map((item, index) => <li key={item} className={cx("list-none border-t pt-2 text-xs", index <= stepIndex ? "border-[#B64B75] text-[#8F355C]" : "border-[#E9C4D5] text-[#A48090]")}>{index + 1}. {stepLabels[item]}</li>)}
            </ol>
          </div>
        </div>
      </header>
      <main className="relative z-10 min-h-0 flex-1 overflow-y-auto px-5 py-8 sm:px-8">
        <div className="mx-auto grid max-w-2xl gap-7">
          <div>
            <p className="m-0 font-serif text-sm italic text-[#B64B75]">CHAPTER {stepIndex + 1} / 4</p>
            <h2 className="mt-1 font-serif text-3xl font-semibold text-[#5E2841]">{stepLabels[step]}</h2>
          </div>
          {step === "role" ? <section className="grid gap-3">{roles.map((role) => {
            const selected = role.id === input.selectedRoleIds[0];
            return <button key={role.id} className={cx("flex min-h-20 items-center gap-3 rounded-md border bg-white/70 p-4 text-left transition-colors", selected ? "border-[#B64B75] bg-[#FFF0F6] shadow-[0_5px_16px_rgba(161,54,100,0.12)]" : "border-[#E9C4D5] hover:border-[#CF7898] hover:bg-white")} type="button" aria-pressed={selected} onClick={() => setInput((current) => ({ ...current, selectedRoleIds: [role.id] }))}>{role.avatarUrl ? <img className="h-11 w-11 rounded-md border border-[#E5B8C9] object-cover" src={role.avatarUrl} alt="" /> : <UserCircle className="h-11 w-11 text-[#A85E7D]" weight="thin" />}<span className="min-w-0 flex-1"><strong className="block font-serif text-base text-[#5E2841]">{role.name}</strong><span className="block truncate text-xs text-[#8B6676]">{role.description}</span></span>{selected ? <Check className="text-[#A93E6A]" weight="bold" /> : null}</button>;
          })}</section> : null}
          {step === "setting" ? <section className="grid gap-5 border-y border-[#E9C4D5] py-5"><label className="grid gap-1.5 text-xs text-[#8B6676]">剧情名称<input className={romanceInputClass} value={input.name} onChange={(event) => setInput((current) => ({ ...current, name: event.target.value }))} /></label><label className="grid gap-1.5 text-xs text-[#8B6676]">开场背景<textarea className={cx(romanceInputClass, "min-h-32 resize-y")} value={input.premise} onChange={(event) => setInput((current) => ({ ...current, premise: event.target.value }))} /></label><label className="grid gap-1.5 text-xs text-[#8B6676]">开始时间（北京时间）<input className={romanceInputClass} type="datetime-local" value={input.firstOc.entryTime} onChange={(event) => updateOc("entryTime", event.target.value)} /></label></section> : null}
          {step === "player" ? <section className="grid gap-5 border-y border-[#E9C4D5] py-5"><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-1.5 text-xs text-[#8B6676]">名称<input className={romanceInputClass} value={input.firstOc.name} onChange={(event) => updateOc("name", event.target.value)} /></label><label className="grid gap-1.5 text-xs text-[#8B6676]">身份<input className={romanceInputClass} value={input.firstOc.identity} onChange={(event) => updateOc("identity", event.target.value)} /></label></div><label className="grid gap-1.5 text-xs text-[#8B6676]">外貌<input className={romanceInputClass} value={input.firstOc.entryLocation} onChange={(event) => updateOc("entryLocation", event.target.value)} /></label></section> : null}
          {step === "review" ? <section className="divide-y divide-[#E9C4D5] border-y border-[#E9C4D5]"><div className="grid gap-1 py-4"><span className="text-xs text-[#A48090]">角色</span><strong className="font-serif text-[#5E2841]">{selectedRole?.name || "未选择"}</strong></div><div className="grid gap-1 py-4"><span className="text-xs text-[#A48090]">剧情</span><strong className="font-serif text-[#5E2841]">{input.name}</strong><span className="text-sm text-[#765667]">{input.premise}</span></div><div className="grid gap-1 py-4"><span className="text-xs text-[#A48090]">玩家</span><strong className="font-serif text-[#5E2841]">{input.firstOc.name}，{input.firstOc.identity}</strong><span className="text-sm text-[#765667]">{input.firstOc.entryLocation} · {input.firstOc.entryTime}</span></div></section> : null}
          {error ? <div className="border border-[#D58A9F] bg-[#FFF0F4] px-3 py-2 text-sm text-[#9A365D]" role="alert">{error}</div> : null}
        </div>
      </main>
      <footer className="relative z-10 border-t border-[#E9C4D5] bg-white/60 px-5 py-4 sm:px-8"><div className="mx-auto flex max-w-2xl justify-between gap-3">{stepIndex ? <button className={cx(ghostButtonClass, "border-[#E5B8C9] bg-white/70 text-[#6C3E52] hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]")} type="button" disabled={busy} onClick={previous}>上一步</button> : <span />}{step === "review" ? <button className={romancePrimaryButtonClass} type="button" disabled={busy || !stepComplete} onClick={() => onCreate(input)}><span className="inline-flex items-center gap-2"><Sparkle weight="fill" />开始剧情</span></button> : <button className={romancePrimaryButtonClass} type="button" disabled={!stepComplete} onClick={next}><span className="inline-flex items-center gap-2">下一步<ArrowRight /></span></button>}</div></footer>
    </section>
  );
}
