import { ArrowLeft, ArrowRight, Check, Sparkle, UserCircle } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { cx, inputClass } from "../shared/styles";
import type { WorldCreationInput, WorldRoleChoice } from "./types";
import { WORLD_MENU_BACKGROUND_URL } from "./worldStaticAssets";
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
  setting: "写下开场",
  player: "留下姓名",
  review: "开始这一页",
};

const fieldClass = cx(inputClass, "border-0 border-b border-[#B8A991] !bg-transparent px-0 text-[#2E3440] focus:!border-[#39495A] focus:ring-0");
const actionClass = "inline-flex min-h-11 items-center gap-2 border border-[#35475A] bg-[#35475A] px-5 text-sm font-semibold text-[#FFF9ED] transition-colors hover:bg-[#283949] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#A9C1CD] disabled:cursor-default disabled:opacity-50";
const paperMotion = { opacity: 1, x: 0 } as const;

/** Renders the narrative-first creation flow without changing the creation contract. */
export function WorldCreateFlow({ roles, initialSeed, busy = false, error = "", onBack, onCreate }: WorldCreateFlowProps) {
  const [input, setInput] = useState(() => createInitialWorldCreationInput(initialSeed));
  const [stepIndex, setStepIndex] = useState(0);
  const reducedMotion = useReducedMotion() ?? false;
  const step = creationSteps[stepIndex];
  const selectedRole = roles.find((role) => role.id === input.selectedRoleIds[0]);
  const stepComplete = isCreationStepComplete(step, input);
  const updateOc = (field: keyof WorldCreationInput["firstOc"], value: string) => setInput((current) => ({ ...current, firstOc: { ...current.firstOc, [field]: value } }));
  const next = () => setStepIndex((current) => Math.min(current + 1, creationSteps.length - 1));
  const previous = () => setStepIndex((current) => Math.max(current - 1, 0));

  return (
    <section className="relative h-full min-h-0 overflow-hidden bg-[#25333D] text-[#2E3440]" data-testid="world-create-flow">
      <div aria-hidden="true" className="absolute inset-0 bg-cover bg-center bg-no-repeat" style={{ backgroundImage: `url(${WORLD_MENU_BACKGROUND_URL})` }} />
      <div aria-hidden="true" className="absolute inset-0 bg-[linear-gradient(90deg,rgba(25,35,43,0.24),transparent_68%)]" />
      <motion.main
        className="relative z-10 flex h-full w-[min(39rem,100%)] flex-col border-r border-[#C8B99F]/70 bg-[#F8F0DF]/[0.96] shadow-[18px_0_48px_rgba(20,29,35,0.18)]"
        data-testid="story-create-letter"
        initial={{ opacity: 0, x: reducedMotion ? 0 : -42 }}
        animate={paperMotion}
        transition={{ duration: reducedMotion ? 0 : 0.48, ease: "easeOut" }}
      >
        <header className="flex items-start gap-4 px-[clamp(20px,4vw,48px)] pb-6 pt-[clamp(20px,5vh,48px)]">
          <button className="grid h-9 w-9 shrink-0 place-items-center border border-[#AFA188] text-[#384755] transition-colors hover:bg-[#EAE0CD] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#8EB0BE]" type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}><ArrowLeft /></button>
          <div className="min-w-0">
            <p className="m-0 text-[11px] font-semibold tracking-[0.2em] text-[#6B7C87]">NEW STORY · {String(stepIndex + 1).padStart(2, "0")}</p>
            <h1 className="m-0 mt-2 font-serif text-[clamp(1.75rem,4vw,2.5rem)] font-semibold leading-none text-[#2F3B47]">{stepLabels[step]}</h1>
          </div>
        </header>

        <div className="grid grid-cols-[auto_1fr] gap-5 border-y border-[#D5C8B0] px-[clamp(20px,4vw,48px)] py-4" aria-label="创建步骤">
          <ol className="m-0 grid content-start gap-3 p-0">
            {creationSteps.map((item, index) => <li key={item} className={cx("grid h-5 w-5 place-items-center rounded-full border text-[10px] font-semibold", index <= stepIndex ? "border-[#435969] bg-[#435969] text-[#FFF9ED]" : "border-[#B9AE99] text-[#857A69]")}>{index + 1}</li>)}
          </ol>
          <ol className="m-0 grid gap-3 p-0">
            {creationSteps.map((item, index) => <li key={item} className={cx("list-none text-xs", index === stepIndex ? "font-semibold text-[#334857]" : "text-[#887D6B]")}>{stepLabels[item]}</li>)}
          </ol>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-[clamp(20px,4vw,48px)] py-8">
          <div className="mx-auto grid max-w-xl gap-7">
            {step === "role" ? <section className="grid gap-2" aria-label="角色列表">{roles.map((role) => {
              const selected = role.id === input.selectedRoleIds[0];
              return <button key={role.id} className={cx("group flex min-h-[76px] items-center gap-4 border-b px-1 py-3 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#8EB0BE]", selected ? "border-[#40596A] bg-[#EEE5D3]" : "border-[#D7CBB6] hover:border-[#798B93] hover:bg-[#F1E8D8]")} type="button" aria-pressed={selected} onClick={() => setInput((current) => ({ ...current, selectedRoleIds: [role.id] }))}>{role.avatarUrl ? <img className="h-12 w-12 border border-[#BBAF99] object-cover" src={role.avatarUrl} alt="" /> : <UserCircle className="h-12 w-12 text-[#71838D]" weight="thin" />}<span className="min-w-0 flex-1"><strong className="block font-serif text-lg text-[#2F3B47]">{role.name}</strong><span className="mt-1 block truncate text-xs text-[#746B5F]">{role.description}</span></span>{selected ? <Check className="shrink-0 text-[#3C5667]" weight="bold" /> : <span className="h-2 w-2 shrink-0 rounded-full bg-[#C5B9A5] transition-colors group-hover:bg-[#768995]" />}</button>;
            })}</section> : null}
            {step === "setting" ? <section className="grid gap-7"><label className="grid gap-2 text-xs text-[#756C60]">剧情名称<input className={fieldClass} value={input.name} onChange={(event) => setInput((current) => ({ ...current, name: event.target.value }))} /></label><label className="grid gap-2 text-xs text-[#756C60]">开场背景<textarea className={cx(fieldClass, "min-h-28 resize-y py-2")} value={input.premise} onChange={(event) => setInput((current) => ({ ...current, premise: event.target.value }))} /></label><label className="grid gap-2 text-xs text-[#756C60]">开始时间（北京时间）<input className={fieldClass} type="datetime-local" value={input.firstOc.entryTime} onChange={(event) => updateOc("entryTime", event.target.value)} /></label></section> : null}
            {step === "player" ? <section className="grid gap-7"><div className="grid gap-7 sm:grid-cols-2"><label className="grid gap-2 text-xs text-[#756C60]">名称<input className={fieldClass} value={input.firstOc.name} onChange={(event) => updateOc("name", event.target.value)} /></label><label className="grid gap-2 text-xs text-[#756C60]">身份<input className={fieldClass} value={input.firstOc.identity} onChange={(event) => updateOc("identity", event.target.value)} /></label></div><label className="grid gap-2 text-xs text-[#756C60]">外貌<input className={fieldClass} value={input.firstOc.entryLocation} onChange={(event) => updateOc("entryLocation", event.target.value)} /></label></section> : null}
            {step === "review" ? <section className="grid gap-6 border-y border-[#D5C8B0] py-6"><div className="grid gap-1"><span className="text-[11px] font-semibold tracking-[0.16em] text-[#7C8B92]">CAST</span><strong className="font-serif text-xl text-[#2F3B47]">{selectedRole?.name || "未选择"}</strong></div><div className="grid gap-1"><span className="text-[11px] font-semibold tracking-[0.16em] text-[#7C8B92]">OPENING</span><strong className="font-serif text-xl text-[#2F3B47]">{input.name}</strong><span className="text-sm leading-6 text-[#625B52]">{input.premise}</span></div><div className="grid gap-1"><span className="text-[11px] font-semibold tracking-[0.16em] text-[#7C8B92]">PLAYER</span><strong className="font-serif text-xl text-[#2F3B47]">{input.firstOc.name}，{input.firstOc.identity}</strong><span className="text-sm text-[#625B52]">{input.firstOc.entryLocation} · {input.firstOc.entryTime}</span></div></section> : null}
            {error ? <div className="border-l-2 border-[#9B4F4E] bg-[#F4DDD5] px-3 py-2 text-sm text-[#803D3E]" role="alert">{error}</div> : null}
          </div>
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-[#D5C8B0] px-[clamp(20px,4vw,48px)] py-5">
          {stepIndex ? <button className="text-sm text-[#526570] transition-colors hover:text-[#263B4B] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#8EB0BE]" type="button" disabled={busy} onClick={previous}>上一步</button> : <span />}
          {step === "review" ? <button className={actionClass} type="button" disabled={busy || !stepComplete} onClick={() => onCreate(input)}><Sparkle weight="fill" />开始剧情</button> : <button className={actionClass} type="button" disabled={!stepComplete} onClick={next}>下一步<ArrowRight /></button>}
        </footer>
      </motion.main>
    </section>
  );
}
