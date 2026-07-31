import { ArrowRight, CaretDown, PaperPlaneTilt, Play } from "@phosphor-icons/react";
import { useState } from "react";
import { AutosizeTextarea } from "../shared/AutosizeTextarea";
import { canSubmitWorldAction } from "./selectors";
import type { DecisionBarrier, SceneBeat, WorldDetails } from "./types";
import type { WorldDialogueSnapshot } from "./worldDialogueGate";

type WorldGameInteractionProps = {
  world: WorldDetails;
  beat: SceneBeat | null;
  paused: boolean;
  performing: boolean;
  busy: boolean;
  dialogue: WorldDialogueSnapshot;
  onContinueDialogue: () => void;
  onSubmitAction: (content: string) => Promise<boolean>;
  onAdvance: () => void;
  onResolveBarrier: (barrier: DecisionBarrier, choiceId: string) => void;
};

/** Renders dialogue and swaps the bottom area to action or barrier input. */
export function WorldGameInteraction({ world, beat, paused, performing, busy, dialogue, onContinueDialogue, onSubmitAction, onAdvance, onResolveBarrier }: WorldGameInteractionProps) {
  const [action, setAction] = useState("");
  const barrier = world.scene.barriers[0] ?? null;
  const canAct = !paused && !performing && canSubmitWorldAction(world);
  const hasDialogue = dialogue.cueId !== null;
  const speakerName = hasDialogue ? dialogue.speakerName : beat?.speakerName ?? "";
  const visibleText = hasDialogue ? dialogue.visibleText : performing ? "" : beat?.content ?? "";

  async function submit() {
    if (!canAct || !action.trim()) return;
    if (await onSubmitAction(action)) setAction("");
  }

  return (
    <section className="pointer-events-none absolute inset-x-0 bottom-0 z-20 px-[clamp(20px,8vw,120px)] pb-[clamp(24px,6vh,64px)]">
      <div className="pointer-events-auto mx-auto max-w-5xl border-l-2 border-[#E59A70] bg-black/55 px-6 py-5 backdrop-blur-md">
        {speakerName ? <h1 className="m-0 mb-2 font-serif text-lg font-semibold text-[#F3B18B]">{speakerName}</h1> : null}
        <p className="m-0 min-h-8 whitespace-pre-wrap font-serif text-lg leading-8 text-white">{visibleText}</p>
        {hasDialogue && !paused ? <button className="ml-auto mt-2 grid h-9 w-9 place-items-center rounded-md text-white/70 hover:bg-white/10 hover:text-white" type="button" aria-label={dialogue.fullyRevealed ? "继续对话" : "显示完整对话"} title={dialogue.fullyRevealed ? "继续对话" : "显示完整对话"} onClick={onContinueDialogue}><CaretDown /></button> : null}
        {paused ? <p className="m-0 mt-3 text-xs text-white/60">演出已暂停</p> : null}
        {!paused && barrier ? (
          <section className="mt-5 grid gap-3" aria-label="待决事件">
            <div><h2 className="m-0 font-serif text-base font-semibold">{barrier.title}</h2><p className="m-0 mt-1 text-sm leading-6 text-white/70">{barrier.context}</p></div>
            <div className="grid gap-2 sm:grid-cols-2">
              {barrier.choices.map((choice) => <button key={choice.id} className="flex min-h-11 items-center justify-between rounded-md border border-white/20 bg-white/10 px-3 text-left text-sm hover:bg-white/15 disabled:opacity-50" type="button" disabled={busy} onClick={() => onResolveBarrier(barrier, choice.id)}><span>{choice.label}</span><ArrowRight /></button>)}
            </div>
          </section>
        ) : null}
        {!paused && canAct ? (
          <div className="mt-5 flex items-end gap-2 rounded-md border border-white/20 bg-black/20 p-2 transition focus-within:border-[#E59A70] focus-within:ring-2 focus-within:ring-[#E59A70]/20">
            <AutosizeTextarea className="min-h-10 w-full bg-transparent px-2 py-2 text-sm leading-6 text-white placeholder:text-white/45 focus:outline-none" containerClassName="min-h-10 flex-1" mirrorClassName="px-2 py-2 text-sm leading-6" value={action} placeholder={world.scene.actionPrompt} onChange={(event) => setAction(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); } }} />
            <button className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-[#A75F41] text-white disabled:opacity-40" type="button" aria-label="提交行动" disabled={busy || !action.trim()} onClick={() => void submit()}><PaperPlaneTilt weight="fill" /></button>
          </div>
        ) : null}
        {!paused && !performing && !barrier && !canAct ? <button className="mt-5 inline-flex h-10 items-center gap-2 rounded-md bg-white/15 px-4 text-sm text-white hover:bg-white/20 disabled:opacity-50" type="button" disabled={busy} onClick={onAdvance}><Play weight="fill" />继续世界</button> : null}
      </div>
    </section>
  );
}
