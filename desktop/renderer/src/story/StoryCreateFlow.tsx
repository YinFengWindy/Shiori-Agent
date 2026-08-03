import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowLeft, ArrowRight, Check, CircleNotch, Sparkle } from "@phosphor-icons/react";
import { useState } from "react";
import { cx } from "../shared/styles";
import type { StoryCreationInput, StoryRoleChoice } from "./types";
import { createInitialStoryCreationInput, creationSteps, isCreationStepComplete, type CreationStep } from "./storyCreationWizard";
import { StoryCreateStep } from "./StoryCreateStep";
import { StorySurface } from "./StorySurface";

type StoryCreateFlowProps = {
  roles: StoryRoleChoice[];
  busy?: boolean;
  error?: string;
  onBack: () => void;
  onCreate: (input: StoryCreationInput) => void;
};

const stepLabels: Record<CreationStep, string> = { role: "选择角色", setting: "开场设定", player: "玩家资料" };
const storyActionButtonBase = "inline-flex min-h-10 min-w-28 items-center justify-center gap-2 whitespace-nowrap rounded-md border-0 px-4 py-2.5 text-sm font-medium transition-[background-color,box-shadow,color,transform] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0] disabled:cursor-default disabled:opacity-50";
const storyPrimaryButtonClass = cx(storyActionButtonBase, "bg-[#B64B75]/90 text-white shadow-[0_8px_20px_rgba(166,57,104,0.18)] hover:bg-[#96325F] hover:shadow-[0_10px_24px_rgba(166,57,104,0.24)] active:scale-[0.98]");
const storySecondaryButtonClass = cx(storyActionButtonBase, "bg-[#FFF8FC]/45 text-[#6C3E52] shadow-[0_6px_16px_rgba(109,53,80,0.08)] hover:bg-white/75 hover:text-[#7A2356] hover:shadow-[0_8px_18px_rgba(109,53,80,0.12)]");
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
    <StorySurface dataTestId="story-create-flow" panelTestId="story-create-panel" contentClassName="overflow-hidden">
      <header>
        <div className="border-b border-[#DDA9BE]/65 px-[clamp(18px,4vw,40px)] py-5">
          <div className="flex items-center gap-4">
            <button className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-[#FFF8FC]/55 text-[#8F355C] transition-colors hover:bg-white hover:text-[#7A2356] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]" type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}><ArrowLeft className="h-5 w-5" weight="bold" /></button>
            <div className="min-w-0 flex-1"><h1 className="m-0 font-serif text-2xl font-semibold italic text-[#7A2356]">新剧情</h1></div>
          </div>
        </div>
        <div className="px-[clamp(18px,4vw,40px)] py-4">
          <ol className="grid grid-cols-3 gap-2" aria-label="创建步骤">
            {creationSteps.map((item, index) => {
              const active = index === stepIndex;
              const complete = index < stepIndex;
              return <li key={item} aria-current={active ? "step" : undefined} className={cx("min-w-0 text-xs transition-colors", active || complete ? "text-[#8F355C]" : "text-[#A48090]")}><div className="mb-1 flex items-center gap-1.5"><span className={cx("grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[10px]", active || complete ? "border-[#B64B75] bg-[#FFF0F6]" : "border-[#E9C4D5] bg-white/60")}>{complete ? <Check weight="bold" /> : index + 1}</span><span className="truncate">{stepLabels[item]}</span></div><div className="h-0.5 overflow-hidden bg-[#E9C4D5]/65"><motion.span className="block h-full origin-left bg-[#B64B75]" initial={false} animate={{ scaleX: active || complete ? 1 : 0 }} transition={stepTransition} /></div></li>;
            })}
          </ol>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-[clamp(18px,4vw,40px)] py-7">
        <div className="mx-auto w-full max-w-3xl">
          <AnimatePresence initial={false} mode="wait">
            <motion.div key={step} initial={stepMotion.initial} animate={stepMotion.animate} exit={stepMotion.exit} transition={reducedMotion ? { duration: 0 } : stepTransition}>
              <StoryCreateStep step={step} roles={roles} input={input} selectedRole={selectedRole} reducedMotion={reducedMotion} onSelectRole={(roleId) => setInput((current) => ({ ...current, roleId }))} onChangeSetting={updateSetting} onChangeProfile={updateProfile} />
            </motion.div>
          </AnimatePresence>
          <AnimatePresence initial={false}>{error ? <motion.div className="mt-5 border border-[#D58A9F] bg-[#FFF0F4] px-3 py-2 text-sm text-[#9A365D]" role="alert" initial={{ opacity: 0, y: reducedMotion ? 0 : 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={reducedMotion ? { duration: 0 } : stepTransition}>{error}</motion.div> : null}</AnimatePresence>
        </div>
      </main>

      <footer className="border-t border-[#DDA9BE]/65 px-[clamp(18px,4vw,40px)] py-5"><div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-4"><div className="min-w-0 flex-1">{stepIndex ? <button className={storySecondaryButtonClass} type="button" disabled={busy} onClick={previous}><ArrowLeft />上一步</button> : null}</div><div className="flex shrink-0 items-center justify-end gap-3">{busy ? <span className="max-w-24 text-right text-xs text-[#7D6470]">正在创建剧情</span> : null}{step === "player" ? <button className={storyPrimaryButtonClass} type="button" disabled={busy || !stepComplete} onClick={() => onCreate(input)}>{busy ? <span className="inline-flex items-center gap-2"><CircleNotch className="animate-spin" />创建中</span> : <span className="inline-flex items-center gap-2"><Sparkle weight="fill" />开始剧情</span>}</button> : <button className={storyPrimaryButtonClass} type="button" disabled={!stepComplete} onClick={next}><span className="inline-flex items-center gap-2">下一步<ArrowRight /></span></button>}</div></div></footer>
    </StorySurface>
  );
}
