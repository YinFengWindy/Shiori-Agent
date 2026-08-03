import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowLeft, ArrowRight, Check, CircleNotch, Sparkle } from "@phosphor-icons/react";
import { useState } from "react";
import { cx, ghostButtonClass } from "../shared/styles";
import type { StoryCreationInput, StoryRoleChoice } from "./types";
import { createInitialStoryCreationInput, creationSteps, isCreationStepComplete, type CreationStep } from "./storyCreationWizard";
import { StoryCreateStep } from "./StoryCreateStep";

type StoryCreateFlowProps = {
  roles: StoryRoleChoice[];
  busy?: boolean;
  error?: string;
  onBack: () => void;
  onCreate: (input: StoryCreationInput) => void;
};

const stepLabels: Record<CreationStep, string> = { role: "选择角色", setting: "开场设定", player: "玩家资料" };
const storyPrimaryButtonClass = "inline-flex min-w-32 items-center justify-center rounded-md border border-[#A93E6A] bg-[#A93E6A] px-[18px] py-3 text-white transition-[background-color,transform] hover:bg-[#902B57] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0] active:scale-[0.98] disabled:cursor-default disabled:opacity-50";
const stepTransition = { duration: 0.22, ease: "easeOut" } as const;

/** Renders the compact animated form that creates one Story database entry. */
export function StoryCreateFlow({ roles, busy = false, error = "", onBack, onCreate }: StoryCreateFlowProps) {
  const [input, setInput] = useState<StoryCreationInput>(createInitialStoryCreationInput);
  const [stepIndex, setStepIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const reducedMotion = useReducedMotion() ?? false;
  const step = creationSteps[stepIndex];
  const selectedRole = roles.find((role) => role.id === input.roleId);
  const stepComplete = isCreationStepComplete(step, input);
  const updateSetting = (field: "title" | "background" | "startsAt", value: string) => setInput((current) => ({ ...current, [field]: value }));
  const updateProfile = (field: keyof StoryCreationInput["playerProfile"], value: string) => setInput((current) => ({ ...current, playerProfile: { ...current.playerProfile, [field]: value } }));
  const goToStep = (nextIndex: number) => {
    setDirection(nextIndex > stepIndex ? 1 : -1);
    setStepIndex(nextIndex);
  };
  const next = () => goToStep(Math.min(stepIndex + 1, creationSteps.length - 1));
  const previous = () => goToStep(Math.max(stepIndex - 1, 0));
  const stepMotion = {
    initial: { opacity: 0, x: reducedMotion ? 0 : direction > 0 ? 18 : -18 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: reducedMotion ? 0 : direction > 0 ? -18 : 18 },
  };

  return (
    <section className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[#FFF8FC] text-[#4A2738]" data-testid="story-create-flow">
      <div aria-hidden="true" className="pointer-events-none absolute inset-[clamp(12px,2vw,28px)] border border-[#E9C4D5]/70" />
      <header className="relative z-10 border-b border-[#E9C4D5] bg-white/60 px-5 py-4 sm:px-8">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-center gap-4">
            <button className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-[#D89AB4]/55 bg-white/65 text-[#8F355C] transition-colors hover:border-[#B64B75] hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]" type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}><ArrowLeft /></button>
            <div className="min-w-0 flex-1"><p className="m-0 font-serif text-sm italic text-[#B64B75] [text-shadow:0_1px_0_rgba(255,255,255,0.9)]">CREATE A STORY</p><h1 className="m-0 mt-0.5 font-serif text-xl font-semibold text-[#5E2841]">新剧情</h1></div>
            <span className="shrink-0 font-serif text-sm text-[#A48090]">{String(stepIndex + 1).padStart(2, "0")} / {String(creationSteps.length).padStart(2, "0")}</span>
          </div>
          <ol className="mt-4 grid grid-cols-3 gap-2" aria-label="创建步骤">
            {creationSteps.map((item, index) => {
              const active = index === stepIndex;
              const complete = index < stepIndex;
              return <li key={item} aria-current={active ? "step" : undefined} className={cx("min-w-0 text-xs transition-colors", active || complete ? "text-[#8F355C]" : "text-[#A48090]")}><div className="mb-1 flex items-center gap-1.5"><span className={cx("grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[10px]", active || complete ? "border-[#B64B75] bg-[#FFF0F6]" : "border-[#E9C4D5] bg-white/60")}>{complete ? <Check weight="bold" /> : index + 1}</span><span className="truncate">{stepLabels[item]}</span></div><div className="h-0.5 overflow-hidden bg-[#E9C4D5]/65"><motion.span className="block h-full origin-left bg-[#B64B75]" initial={false} animate={{ scaleX: active || complete ? 1 : 0 }} transition={stepTransition} /></div></li>;
            })}
          </ol>
        </div>
      </header>

      <main className="relative z-10 min-h-0 flex-1 overflow-y-auto px-5 py-7 sm:px-8">
        <div className="mx-auto max-w-3xl">
          <div className="mb-6 flex items-end justify-between gap-4"><div><p className="m-0 font-serif text-sm italic text-[#B64B75]">{String(stepIndex + 1).padStart(2, "0")} / {String(creationSteps.length).padStart(2, "0")}</p><h2 className="mt-1 font-serif text-3xl font-semibold text-[#5E2841]">{stepLabels[step]}</h2></div><span className="hidden text-xs text-[#A48090] sm:block">{selectedRole?.name || ""}</span></div>
          <AnimatePresence initial={false} mode="wait">
            <motion.div key={step} initial={stepMotion.initial} animate={stepMotion.animate} exit={stepMotion.exit} transition={reducedMotion ? { duration: 0 } : stepTransition}>
              <StoryCreateStep step={step} roles={roles} input={input} selectedRole={selectedRole} reducedMotion={reducedMotion} onSelectRole={(roleId) => setInput((current) => ({ ...current, roleId }))} onChangeSetting={updateSetting} onChangeProfile={updateProfile} />
            </motion.div>
          </AnimatePresence>
          <AnimatePresence initial={false}>{error ? <motion.div className="mt-5 border border-[#D58A9F] bg-[#FFF0F4] px-3 py-2 text-sm text-[#9A365D]" role="alert" initial={{ opacity: 0, y: reducedMotion ? 0 : 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={reducedMotion ? { duration: 0 } : stepTransition}>{error}</motion.div> : null}</AnimatePresence>
        </div>
      </main>

      <footer className="relative z-10 border-t border-[#E9C4D5] bg-white/60 px-5 py-4 sm:px-8"><div className="mx-auto flex max-w-3xl items-center justify-between gap-3"><div className="min-w-24 text-xs text-[#A48090]">{busy ? "正在创建剧情" : ""}</div>{stepIndex ? <button className={cx(ghostButtonClass, "inline-flex items-center gap-1.5 border-[#E5B8C9] bg-white/70 text-[#6C3E52] hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]")} type="button" disabled={busy} onClick={previous}><ArrowLeft />上一步</button> : <span className="min-w-24" aria-hidden="true" />}{step === "player" ? <button className={storyPrimaryButtonClass} type="button" disabled={busy || !stepComplete} onClick={() => onCreate(input)}>{busy ? <span className="inline-flex items-center gap-2"><CircleNotch className="animate-spin" />创建中</span> : <span className="inline-flex items-center gap-2"><Sparkle weight="fill" />开始剧情</span>}</button> : <button className={storyPrimaryButtonClass} type="button" disabled={!stepComplete} onClick={next}><span className="inline-flex items-center gap-2">下一步<ArrowRight /></span></button>}</div></footer>
    </section>
  );
}
