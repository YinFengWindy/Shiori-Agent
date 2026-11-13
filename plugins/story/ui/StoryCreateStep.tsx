import { Check, UserCircle } from "@phosphor-icons/react";
import { motion } from "motion/react";
import { useLayoutEffect, useRef } from "react";
import { cx } from "@yinfengwindy/shiori-sdk";
import type { StoryCreationInput, StoryRoleChoice } from "./types";
import type { CreationStep } from "./storyCreationWizard";
import { STORY_TIME_BANDS, normalizeStoryTimeBand } from "./storyTime";
import { storyEmptyTextClass, storyFieldLabelClass, storyInputClass, storySegmentOptionClass, storySegmentTrackClass } from "./storyStyles";

type StoryCreateStepProps = {
  step: CreationStep;
  roles: StoryRoleChoice[];
  input: StoryCreationInput;
  selectedRole?: StoryRoleChoice;
  reducedMotion: boolean;
  onSelectRole: (roleId: string) => void;
  onChangeSetting: (field: "title" | "background" | "storyDate" | "timeBand", value: string) => void;
  onChangeProfile: (field: keyof StoryCreationInput["playerProfile"], value: string) => void;
};

const roleCardClass = "flex min-h-20 items-center gap-3 rounded-md border bg-[color:var(--story-paper-strong)] p-4 text-left transition-[border-color,background-color,box-shadow] hover:border-[color:var(--story-line-strong)]";
const sectionClass = "border-y border-[color:var(--story-line-field)]";
const reviewLabelClass = "text-xs text-[color:var(--story-ink-muted)]";
const reviewValueClass = "font-serif text-[color:var(--story-ink-strong)]";
const stepItemTransition = { duration: 0.22, ease: "easeOut" } as const;

/** Renders the focused fields or the final creation review for the active step. */
export function StoryCreateStep({ step, roles, input, selectedRole, reducedMotion, onSelectRole, onChangeSetting, onChangeProfile }: StoryCreateStepProps) {
  const backgroundRef = useRef<HTMLTextAreaElement | null>(null);

  useLayoutEffect(() => {
    const textarea = backgroundRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [input.background]);

  if (step === "role") {
    return (
      <section className="grid gap-3" data-testid="story-create-step">
        {roles.length ? roles.map((role, index) => {
          const selected = role.id === input.roleId;
          return (
            <motion.button
              key={role.id}
              className={cx(roleCardClass, selected ? "border-[color:var(--story-line-strong)] !bg-[color:var(--story-paper-selected)] shadow-[var(--story-shadow-selected)]" : "border-[color:var(--story-line-field)]")}
              type="button"
              aria-pressed={selected}
              initial={{ opacity: 0, y: reducedMotion ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ ...stepItemTransition, delay: reducedMotion ? 0 : index * 0.04 }}
              whileTap={reducedMotion ? undefined : { scale: 0.985 }}
              onClick={() => onSelectRole(role.id)}
            >
              {role.avatarUrl ? <img className="h-11 w-11 rounded-md border border-[color:var(--story-line-field)] object-cover" src={role.avatarUrl} alt="" /> : <UserCircle className="h-11 w-11 text-[color:var(--story-rose)]" weight="thin" />}
              <span className="min-w-0 flex-1"><strong className="block font-serif text-base text-[color:var(--story-ink-strong)]">{role.name}</strong><span className="block truncate text-xs text-[color:var(--story-ink-muted)]">{role.description}</span></span>
              <motion.span initial={false} animate={{ opacity: selected ? 1 : 0, scale: selected ? 1 : 0.7 }} transition={stepItemTransition}><Check className="text-[color:var(--story-wine)]" weight="bold" /></motion.span>
            </motion.button>
          );
        }) : <p className={storyEmptyTextClass}>暂无可用角色</p>}
      </section>
    );
  }

  if (step === "setting") {
    return (
      <section className={cx("grid gap-5 py-5", sectionClass)} data-testid="story-create-step">
        <label className={storyFieldLabelClass}>剧情名称<input className={storyInputClass} value={input.title} onChange={(event) => onChangeSetting("title", event.target.value)} /></label>
        <label className={storyFieldLabelClass}>开场背景<textarea ref={backgroundRef} className={cx(storyInputClass, "min-h-32 resize-none overflow-hidden")} value={input.background} onChange={(event) => onChangeSetting("background", event.target.value)} /></label>
        <label className={storyFieldLabelClass}>开始日期<input className={storyInputClass} type="date" value={input.storyDate} onChange={(event) => onChangeSetting("storyDate", event.target.value)} /></label>
        <div className={storyFieldLabelClass}>
          <span id="story-create-time-band">开始时段</span>
          <div className={cx(storySegmentTrackClass, "grid-cols-5")} role="radiogroup" aria-labelledby="story-create-time-band">
            {STORY_TIME_BANDS.map((band) => {
              const selected = normalizeStoryTimeBand(input.timeBand) === band;
              return <button key={band} className={storySegmentOptionClass(selected)} type="button" role="radio" aria-checked={selected} onClick={() => onChangeSetting("timeBand", band)}>{band}</button>;
            })}
          </div>
        </div>
      </section>
    );
  }

  if (step === "player") {
    return (
      <section data-testid="story-create-step">
        <div className={cx("grid gap-4 py-5 sm:grid-cols-2", sectionClass)}>
          <label className={storyFieldLabelClass}>名称<input className={storyInputClass} value={input.playerProfile.displayName} onChange={(event) => onChangeProfile("displayName", event.target.value)} /></label>
          <label className={storyFieldLabelClass}>身份<input className={storyInputClass} value={input.playerProfile.identity} onChange={(event) => onChangeProfile("identity", event.target.value)} /></label>
          <label className={cx(storyFieldLabelClass, "sm:col-span-2")}>外貌<input className={storyInputClass} value={input.playerProfile.appearance} onChange={(event) => onChangeProfile("appearance", event.target.value)} /></label>
        </div>
      </section>
    );
  }

  return (
    <section className={cx("divide-y divide-[color:var(--story-line-field)]", sectionClass)} data-testid="story-create-step" aria-label="剧情总览">
      <div className="grid gap-1 py-4"><span className={reviewLabelClass}>角色</span><strong className={reviewValueClass}>{selectedRole?.name || "未选择"}</strong></div>
      <div className="grid gap-1 py-4"><span className={reviewLabelClass}>剧情</span><strong className={reviewValueClass}>{input.title}</strong><span className="whitespace-pre-wrap text-sm text-[color:var(--story-ink)]">{input.background}</span><span className="text-xs text-[color:var(--story-ink-muted)]">开始日期：{input.storyDate}</span><span className="text-xs text-[color:var(--story-ink-muted)]">开始时段：{normalizeStoryTimeBand(input.timeBand)}</span></div>
      <div className="grid gap-1 py-4"><span className={reviewLabelClass}>玩家</span><strong className={reviewValueClass}>{input.playerProfile.displayName}，{input.playerProfile.identity}</strong><span className="text-sm text-[color:var(--story-ink)]">{input.playerProfile.appearance}</span></div>
    </section>
  );
}
