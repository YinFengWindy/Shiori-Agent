import { StoryError } from "./StoryError";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowRight, Check, CircleNotch, Sparkle } from "@phosphor-icons/react";
import { useRef, useState } from "react";
import { cx } from "@yinfengwindy/shiori-sdk";
import type { StoryCreationInput, StoryRoleChoice } from "./types";
import { createInitialStoryCreationInput, creationSteps, isCreationStepComplete, type CreationStep } from "./storyCreationWizard";
import { StoryCreateStep } from "./StoryCreateStep";
import { StorySurface } from "./StorySurface";
import { useStoryReducedMotion } from "./storyPreferences";
import { storyGutterClass, storyIconButtonClass, storyPageHeaderClass, storyPageTitleClass, storyPrimaryButtonClass, storySecondaryButtonClass } from "./storyStyles";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StoryCreateFlowProps = {
  roles: StoryRoleChoice[];
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  busy?: boolean;
  error?: string;
  errorDetail?: string;
  onBack: () => void;
  onCreate: (input: StoryCreationInput, creationId: string) => void;
};

const stepLabels: Record<CreationStep, string> = { role: "选择角色", setting: "开场设定", player: "玩家资料", review: "总览" };
const stepTransition = { duration: 0.22, ease: "easeOut" } as const;

/** Renders the compact animated form that creates one Story database entry. */
export function StoryCreateFlow({ roles, background, sharedBackdrop = false, busy = false, error = "", errorDetail, onBack, onCreate }: StoryCreateFlowProps) {
  const [input, setInput] = useState<StoryCreationInput>(createInitialStoryCreationInput);
  const [stepIndex, setStepIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const creationAttempt = useRef<{ fingerprint: string; id: string } | null>(null);
  const reducedMotion = useStoryReducedMotion();
  const step = creationSteps[stepIndex];
  const selectedRole = roles.find((role) => role.id === input.roleId);
  const stepComplete = isCreationStepComplete(step, input);
  const updateSetting = (field: "title" | "background" | "storyDate" | "timeBand", value: string) => setInput((current) => ({ ...current, [field]: value }));
  const updateProfile = (field: keyof StoryCreationInput["playerProfile"], value: string) => setInput((current) => ({ ...current, playerProfile: { ...current.playerProfile, [field]: value } }));
  const goToStep = (nextIndex: number) => {
    setDirection(nextIndex > stepIndex ? 1 : -1);
    setStepIndex(nextIndex);
  };
  const next = () => goToStep(Math.min(stepIndex + 1, creationSteps.length - 1));
  const previous = () => goToStep(Math.max(stepIndex - 1, 0));
  const submitCreation = () => {
    const fingerprint = JSON.stringify(input);
    const current = creationAttempt.current;
    const attempt = current?.fingerprint === fingerprint
      ? current
      : { fingerprint, id: crypto.randomUUID() };
    creationAttempt.current = attempt;
    onCreate(input, attempt.id);
  };
  const stepMotion = {
    initial: { opacity: 0, x: reducedMotion ? 0 : direction > 0 ? 18 : -18 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: reducedMotion ? 0 : direction > 0 ? -18 : 18 },
  };

  return (
    <StorySurface background={background} sharedBackdrop={sharedBackdrop} dataTestId="story-create-flow" panelTestId="story-create-panel" contentClassName="overflow-hidden">
      <header>
        <div className={storyPageHeaderClass}>
          <button className={storyIconButtonClass} type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}><ArrowLeft className="h-5 w-5" weight="bold" /></button>
          <h1 className={`${storyPageTitleClass} min-w-0 flex-1`}>新的故事</h1>
        </div>
        <div className={`${storyGutterClass} py-4`}>
          <ol className="m-0 mx-auto grid w-full max-w-3xl list-none grid-cols-4 gap-2 p-0" aria-label="创建步骤">
            {creationSteps.map((item, index) => {
              const active = index === stepIndex;
              const complete = index < stepIndex;
              const reachable = index < stepIndex;
              return <li key={item} aria-current={active ? "step" : undefined} className={cx("min-w-0 text-xs transition-colors", active || complete ? "text-[color:var(--story-wine)]" : "text-[color:var(--story-ink-muted)]")}>
                <button className="mb-1 flex w-full min-w-0 items-center gap-1.5 rounded-sm text-left disabled:cursor-default" type="button" disabled={!reachable || busy} onClick={() => goToStep(index)}>
                  <span className={cx("grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[10px]", active || complete ? "border-[color:var(--story-rose)] bg-[color:var(--story-paper-selected)]" : "border-[color:var(--story-line-field)] bg-[color:var(--story-paper-soft)]")}>{complete ? <Check weight="bold" /> : index + 1}</span>
                  <span className="truncate">{stepLabels[item]}</span>
                </button>
                <div className="h-0.5 overflow-hidden bg-[color:var(--story-line-soft)]"><motion.span className="block h-full origin-left bg-[color:var(--story-rose)]" initial={false} animate={{ scaleX: active || complete ? 1 : 0 }} transition={stepTransition} /></div>
              </li>;
            })}
          </ol>
        </div>
      </header>

      <main className={`min-h-0 flex-1 overflow-y-auto py-7 ${storyGutterClass}`}>
        <div className="mx-auto w-full max-w-3xl">
          <AnimatePresence initial={false} mode="wait">
            <motion.div key={step} initial={stepMotion.initial} animate={stepMotion.animate} exit={stepMotion.exit} transition={reducedMotion ? { duration: 0 } : stepTransition}>
              <StoryCreateStep step={step} roles={roles} input={input} selectedRole={selectedRole} reducedMotion={reducedMotion} onSelectRole={(roleId) => setInput((current) => ({ ...current, roleId }))} onChangeSetting={updateSetting} onChangeProfile={updateProfile} />
            </motion.div>
          </AnimatePresence>
          <AnimatePresence initial={false}>{error ? <motion.div className="mt-5" initial={{ opacity: 0, y: reducedMotion ? 0 : 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={reducedMotion ? { duration: 0 } : stepTransition}><StoryError message={error} detail={errorDetail} /></motion.div> : null}</AnimatePresence>
        </div>
      </main>

      <footer className={`border-t border-[color:var(--story-line)] py-5 ${storyGutterClass}`}>
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-4">
          <div className="min-w-0 flex-1">{stepIndex ? <button className={storySecondaryButtonClass} type="button" disabled={busy} onClick={previous}><ArrowLeft className="h-4 w-4" aria-hidden="true" />上一步</button> : null}</div>
          {step === "review"
            ? <button className={storyPrimaryButtonClass} type="button" disabled={busy || !stepComplete} onClick={submitCreation}>{busy ? <CircleNotch className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Sparkle className="h-4 w-4" weight="fill" aria-hidden="true" />}{busy ? "正在创建" : "开始剧情"}</button>
            : <button className={storyPrimaryButtonClass} type="button" disabled={!stepComplete} onClick={next}>下一步<ArrowRight className="h-4 w-4" aria-hidden="true" /></button>}
        </div>
      </footer>
    </StorySurface>
  );
}
