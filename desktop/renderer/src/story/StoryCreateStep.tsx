import { Check, UserCircle } from "@phosphor-icons/react";
import { motion } from "motion/react";
import { useLayoutEffect, useRef } from "react";
import { cx, inputClass } from "../shared/styles";
import type { StoryCreationInput, StoryRoleChoice } from "./types";
import type { CreationStep } from "./storyCreationWizard";
import { STORY_TIME_BANDS, normalizeStoryTimeBand } from "./storyTime";

type StoryCreateStepProps = {
  step: CreationStep;
  roles: StoryRoleChoice[];
  input: StoryCreationInput;
  selectedRole?: StoryRoleChoice;
  reducedMotion: boolean;
  onSelectRole: (roleId: string) => void;
  onChangeSetting: (field: "title" | "background" | "timeBand", value: string) => void;
  onChangeProfile: (field: keyof StoryCreationInput["playerProfile"], value: string) => void;
};

const storyInputClass = cx(inputClass, "border-[#E5B8C9] !bg-white/85 text-[#4A2738] focus:!border-[#BF5C83] focus:ring-2 focus:ring-[#EFC7D7]/55");
const roleCardClass = "flex min-h-20 items-center gap-3 rounded-md border bg-white/70 p-4 text-left transition-[border-color,background-color,box-shadow,transform] hover:border-[#CF7898] hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]";
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
              className={cx(roleCardClass, selected ? "border-[#B64B75] bg-[#FFF0F6] shadow-[0_5px_16px_rgba(161,54,100,0.12)]" : "border-[#E9C4D5]")}
              type="button"
              aria-pressed={selected}
              initial={{ opacity: 0, y: reducedMotion ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ ...stepItemTransition, delay: reducedMotion ? 0 : index * 0.04 }}
              whileTap={reducedMotion ? undefined : { scale: 0.985 }}
              onClick={() => onSelectRole(role.id)}
            >
              {role.avatarUrl ? <img className="h-11 w-11 rounded-md border border-[#E5B8C9] object-cover" src={role.avatarUrl} alt="" /> : <UserCircle className="h-11 w-11 text-[#A85E7D]" weight="thin" />}
              <span className="min-w-0 flex-1"><strong className="block font-serif text-base text-[#5E2841]">{role.name}</strong><span className="block truncate text-xs text-[#8B6676]">{role.description}</span></span>
              <motion.span initial={false} animate={{ opacity: selected ? 1 : 0, scale: selected ? 1 : 0.7 }} transition={stepItemTransition}><Check className="text-[#A93E6A]" weight="bold" /></motion.span>
            </motion.button>
          );
        }) : <p className="m-0 border-y border-[#E9C4D5] py-5 text-sm text-[#8B6676]">暂无可用角色。</p>}
      </section>
    );
  }

  if (step === "setting") {
    return (
      <section className="grid gap-5 border-y border-[#E9C4D5] py-5" data-testid="story-create-step">
        <label className="grid gap-1.5 text-xs text-[#8B6676]">剧情名称<input className={storyInputClass} value={input.title} onChange={(event) => onChangeSetting("title", event.target.value)} /></label>
        <label className="grid gap-1.5 text-xs text-[#8B6676]">开场背景<textarea ref={backgroundRef} className={cx(storyInputClass, "min-h-32 resize-none overflow-hidden")} value={input.background} onChange={(event) => onChangeSetting("background", event.target.value)} /></label>
        <div className="grid gap-2 text-xs text-[#8B6676]" aria-label="开始时段">
          <span>开始时段</span>
          <div className="grid grid-cols-5 overflow-hidden rounded-md border border-[#D9A5B9]/80 bg-[#FFF8FC]/65 p-1" role="radiogroup" aria-label="开始时间段">
            {STORY_TIME_BANDS.map((band) => {
              const selected = normalizeStoryTimeBand(input.timeBand) === band;
              return <button key={band} className={selected ? "min-h-10 rounded-[3px] bg-[#7A2356] px-2 py-1.5 text-xs font-semibold text-white shadow-[0_4px_12px_rgba(93,21,51,0.18)] transition-colors" : "min-h-10 rounded-[3px] px-2 py-1.5 text-xs font-medium text-[#7A2356]/70 transition-colors hover:bg-white/80 hover:text-[#7A2356]"} type="button" role="radio" aria-checked={selected} onClick={() => onChangeSetting("timeBand", band)}>{band}</button>;
            })}
          </div>
        </div>
      </section>
    );
  }

  if (step === "player") {
    return (
      <section data-testid="story-create-step">
        <div className="grid gap-4 border-y border-[#E9C4D5] py-5 sm:grid-cols-2">
          <label className="grid gap-1.5 text-xs text-[#8B6676]">名称<input className={storyInputClass} value={input.playerProfile.displayName} onChange={(event) => onChangeProfile("displayName", event.target.value)} /></label>
          <label className="grid gap-1.5 text-xs text-[#8B6676]">身份<input className={storyInputClass} value={input.playerProfile.identity} onChange={(event) => onChangeProfile("identity", event.target.value)} /></label>
          <label className="grid gap-1.5 text-xs text-[#8B6676] sm:col-span-2">外貌<input className={storyInputClass} value={input.playerProfile.appearance} onChange={(event) => onChangeProfile("appearance", event.target.value)} /></label>
        </div>
      </section>
    );
  }

  return (
    <section className="divide-y divide-[#E9C4D5] border-y border-[#E9C4D5]" data-testid="story-create-step" aria-label="剧情总览">
      <div className="grid gap-1 py-4"><span className="text-xs text-[#A48090]">角色</span><strong className="font-serif text-[#5E2841]">{selectedRole?.name || "未选择"}</strong></div>
      <div className="grid gap-1 py-4"><span className="text-xs text-[#A48090]">剧情</span><strong className="font-serif text-[#5E2841]">{input.title}</strong><span className="whitespace-pre-wrap text-sm text-[#765667]">{input.background}</span><span className="text-xs text-[#8B6676]">开始时段：{normalizeStoryTimeBand(input.timeBand)}</span></div>
      <div className="grid gap-1 py-4"><span className="text-xs text-[#A48090]">玩家</span><strong className="font-serif text-[#5E2841]">{input.playerProfile.displayName}，{input.playerProfile.identity}</strong><span className="text-sm text-[#765667]">{input.playerProfile.appearance}</span></div>
    </section>
  );
}
