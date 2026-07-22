import { ArrowRight, PaperPlaneTilt, Play } from "@phosphor-icons/react";
import { useState } from "react";
import { AutosizeTextarea } from "../shared/AutosizeTextarea";
import { cx } from "../shared/styles";
import { canSubmitWorldAction } from "./selectors";
import { SceneShot } from "./SceneShot";
import type { DecisionBarrier, WorldDetails } from "./types";

type WorldScenePanelProps = {
  world: WorldDetails;
  busy: boolean;
  onSubmitAction: (content: string) => Promise<boolean>;
  onAdvance: () => void;
  onResolveBarrier: (barrier: DecisionBarrier, choiceId: string) => void;
  onRedrawShot: (shotId: string) => void;
};

/** Renders committed narrative beats and the current world-control surface. */
export function WorldScenePanel({ world, busy, onSubmitAction, onAdvance, onResolveBarrier, onRedrawShot }: WorldScenePanelProps) {
  const [action, setAction] = useState("");
  const barrier = world.scene.barriers[0] ?? null;
  const canAct = canSubmitWorldAction(world);

  async function submit() {
    if (!canAct || !action.trim()) return;
    if (await onSubmitAction(action)) setAction("");
  }

  return (
    <main className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] bg-[#F8F8F6]">
      <header className="border-b border-[#E6E5E0] bg-white/85 px-6 py-4">
        <h1 className="m-0 font-serif text-xl font-semibold text-[#242625]">{world.scene.title}</h1>
        <p className="m-0 mt-1 text-xs text-[#747875]">{world.scene.location} · {world.scene.timeLabel}</p>
      </header>
      <div className="min-h-0 overflow-y-auto px-6 py-5">
        <div className="mx-auto grid w-full max-w-3xl gap-5">
          {world.scene.beats.map((beat) => (
            <article key={beat.id} className={cx("grid gap-2", beat.kind === "dialogue" && "pl-5")} data-testid="scene-beat">
              {beat.shot ? <SceneShot shot={beat.shot} onRedraw={onRedrawShot} /> : null}
              {beat.speakerName ? <h3 className="m-0 text-xs font-semibold text-[#B66D4C]">{beat.speakerName}</h3> : null}
              <p className={cx("m-0 whitespace-pre-wrap text-[15px] leading-7 text-[#303330]", beat.kind !== "dialogue" && "font-serif italic text-[#5B615D]")}>{beat.content}</p>
            </article>
          ))}
        </div>
      </div>
      <footer className="border-t border-[#E3E1DB] bg-white px-6 py-4">
        <div className="mx-auto w-full max-w-3xl">
          {barrier ? (
            <section className="grid gap-3" aria-label="待决事件">
              <div><h2 className="m-0 font-serif text-base font-semibold">{barrier.title}</h2><p className="m-0 mt-1 text-sm leading-6 text-[#686D69]">{barrier.context}</p></div>
              <div className="grid gap-2 sm:grid-cols-2">
                {barrier.choices.map((choice) => <button key={choice.id} className="flex min-h-11 items-center justify-between rounded-md border border-[#D9D6CF] bg-[#FAF9F6] px-3 text-left text-sm hover:border-[#C58A6D]" type="button" disabled={busy} onClick={() => onResolveBarrier(barrier, choice.id)}><span>{choice.label}</span><ArrowRight /></button>)}
              </div>
            </section>
          ) : canAct ? (
            <div className="flex items-end gap-2 rounded-md border border-[#D8DCE2] bg-[#F5F6F5] p-2 transition focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20">
              <AutosizeTextarea className="min-h-10 w-full bg-transparent px-2 py-2 text-sm leading-6 focus:outline-none" containerClassName="min-h-10 flex-1" mirrorClassName="px-2 py-2 text-sm leading-6" value={action} placeholder={world.scene.actionPrompt} onChange={(event) => setAction(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); } }} />
              <button className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-primary text-white disabled:opacity-40" type="button" aria-label="提交行动" disabled={busy || !action.trim()} onClick={() => void submit()}><PaperPlaneTilt weight="fill" /></button>
            </div>
          ) : (
            <button className="inline-flex h-10 items-center gap-2 rounded-md bg-[#343A36] px-4 text-sm text-white disabled:opacity-50" type="button" disabled={busy || world.status === "running"} onClick={onAdvance}><Play weight="fill" />{world.status === "running" ? "世界正在推进" : "继续世界"}</button>
          )}
        </div>
      </footer>
    </main>
  );
}
