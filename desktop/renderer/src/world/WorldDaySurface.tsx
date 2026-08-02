import { ArrowRight, Gear, SignOut } from "@phosphor-icons/react";
import { useLayoutEffect, useRef, useState } from "react";
import { AutosizeTextarea } from "../shared/AutosizeTextarea";
import type { WorldDetails } from "./types";

type WorldDaySurfaceProps = {
  world: WorldDetails;
  busy: boolean;
  error: string;
  onCompleteDay: (content: string) => Promise<boolean>;
  onOpenSettings: () => void;
  onExit: () => void;
};

/** Renders the Story chronicle and its single player-input command. */
export function WorldDaySurface({ world, busy, error, onCompleteDay, onOpenSettings, onExit }: WorldDaySurfaceProps) {
  const [action, setAction] = useState("");
  const currentDayRef = useRef<HTMLElement | null>(null);
  const canCompleteDay = world.status !== "running" && !busy && Boolean(action.trim());

  useLayoutEffect(() => {
    currentDayRef.current?.scrollIntoView({ block: "start" });
  }, [world.currentDayIndex, world.id]);

  async function completeDay() {
    if (!canCompleteDay) return;
    if (await onCompleteDay(action.trim())) setAction("");
  }

  return (
    <section className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-[#F1F4F2] text-[#252A27]" data-testid="world-day-surface">
      <header className="flex min-h-16 items-center justify-between gap-4 border-b border-[#D9DEDA] bg-white px-5">
        <div className="min-w-0">
          <h1 className="m-0 truncate font-serif text-lg font-semibold">{world.name}</h1>
          <p className="m-0 truncate text-xs text-[#707873]">{world.premise}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button className="grid h-9 w-9 place-items-center rounded-md hover:bg-[#EEF1EF]" type="button" aria-label="剧情设置" title="剧情设置" onClick={onOpenSettings}><Gear /></button>
          <button className="grid h-9 w-9 place-items-center rounded-md hover:bg-[#EEF1EF]" type="button" aria-label="返回剧情列表" title="返回剧情列表" onClick={onExit}><SignOut /></button>
        </div>
      </header>
      <div className="min-h-0 overflow-y-auto px-5 py-8">
        <main className="mx-auto grid max-w-3xl gap-12">
          {world.days.map((day) => (
            <section
              key={day.dayIndex}
              ref={day.status === "current" ? currentDayRef : undefined}
              aria-labelledby={`world-day-${day.dayIndex}`}
              className={day.status === "completed" ? "opacity-75" : "scroll-mt-8"}
              data-current-day={day.status === "current" ? "true" : undefined}
            >
              <div className="mb-6 flex items-baseline justify-between gap-4 border-b border-[#CCD3CE] pb-3">
                <h2 id={`world-day-${day.dayIndex}`} className="m-0 font-serif text-2xl font-semibold">{day.title}</h2>
                <span className="text-xs text-[#727A75]">{day.status === "current" ? "进行中" : "已结束"}</span>
              </div>
              <ol className="m-0 grid list-none gap-0 border-l border-[#B9C3BC] pl-7">
                {day.events.map((event) => (
                  <li key={event.id} className="relative pb-7">
                    <span className={`absolute -left-[33px] top-1 h-3 w-3 rounded-full border-2 border-[#F1F4F2] ${event.presentationMode === "scene" ? "bg-[#A75F41]" : "bg-[#66766C]"}`} />
                    <div className="flex items-start justify-between gap-5">
                      <div className="min-w-0">
                        {event.speakerName ? <p className="m-0 mb-1 text-xs font-medium text-[#A75F41]">{event.speakerName}</p> : null}
                        <p className="m-0 whitespace-pre-wrap font-serif text-base leading-7 text-[#3B423E]">{event.content}</p>
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
              {day.status === "current" ? (
                <div className="ml-7 border-t border-[#CDD4CF] pt-5">
                  <div className="flex items-end gap-2 rounded-md border border-[#CCD4CE] bg-white p-2 transition focus-within:border-[#7C8D82] focus-within:ring-2 focus-within:ring-[#7C8D82]/20">
                    <AutosizeTextarea className="min-h-11 w-full bg-transparent px-2 py-2 text-sm leading-6 focus:outline-none" containerClassName="min-h-11 flex-1" mirrorClassName="px-2 py-2 text-sm leading-6" value={action} placeholder={world.scene.actionPrompt} onChange={(event) => setAction(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void completeDay(); } }} />
                    <button className="inline-flex h-10 shrink-0 items-center gap-2 rounded-md bg-[#53675B] px-4 text-sm text-white hover:bg-[#43564B] disabled:opacity-40" type="button" aria-label="提交剧情行动" disabled={!canCompleteDay} onClick={() => void completeDay()}>提交<ArrowRight /></button>
                  </div>
                  {world.status === "running" ? <p className="m-0 mt-2 text-xs text-[#8C513D]">剧情正在生成。</p> : null}
                </div>
              ) : null}
            </section>
          ))}
        </main>
        {error ? <div className="fixed bottom-5 left-1/2 -translate-x-1/2 rounded-md bg-[#793F36] px-4 py-2 text-sm text-white shadow-lg" role="alert">{error}</div> : null}
      </div>
    </section>
  );
}
