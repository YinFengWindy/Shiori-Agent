import { ArrowLeft } from "@phosphor-icons/react";
import { useLayoutEffect, useRef } from "react";
import { DEFAULT_STORY_MENU_BACKGROUND } from "./StoryMenuScene";
import { buildStoryArchiveDays } from "./storyArchivePresentation";
import type { StoryDetails } from "./types";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StoryArchiveSurfaceProps = {
  story: StoryDetails;
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  error: string;
  onReturnToGame: () => void;
};

/** Renders the immutable Story beat history without exposing gameplay input controls. */
export function StoryArchiveSurface({ story, background = DEFAULT_STORY_MENU_BACKGROUND, sharedBackdrop = false, error, onReturnToGame }: StoryArchiveSurfaceProps) {
  const latestEntryRef = useRef<HTMLLIElement | null>(null);
  const archiveDays = buildStoryArchiveDays(story);
  const lastEntryId = archiveDays.at(-1)?.periods.at(-1)?.entries.at(-1)?.id;

  useLayoutEffect(() => {
    latestEntryRef.current?.scrollIntoView({ block: "nearest" });
  }, [lastEntryId]);

  return (
    <section className={`relative h-full min-h-0 overflow-hidden text-white ${sharedBackdrop ? "bg-transparent" : "bg-[#1D1520]"}`} data-testid="story-archive-surface">
      {sharedBackdrop ? null : <div aria-hidden="true" className="absolute inset-0 bg-cover bg-center bg-no-repeat" data-testid="story-archive-backdrop" style={{ backgroundImage: `url(${background.url})` }} />}
      <div aria-hidden="true" className={`absolute inset-0 bg-[#F1F4F2]/82 ${sharedBackdrop ? "" : "backdrop-blur-sm"}`} />
      <div className="relative z-10 grid h-full min-h-0 grid-rows-[minmax(0,1fr)]">
        <div className="pointer-events-none absolute right-5 top-5 z-10 flex gap-2">
        <button className="pointer-events-auto grid h-9 w-9 place-items-center rounded-md text-[#5D6C63] transition-colors hover:bg-white/75 hover:text-[#35433A] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7C8D82]/35" type="button" aria-label="返回游戏页" title="返回游戏页" onClick={onReturnToGame}><ArrowLeft /></button>
        </div>
        <div className="min-h-0 overflow-y-auto px-5 py-8">
        <main className="mx-auto grid max-w-3xl gap-8">
          <header className="border-b border-white/25 pb-4"><p className="story-archive-readable m-0 text-xs text-white/70">剧情记录</p><h1 className="story-archive-readable m-0 mt-1 text-2xl font-semibold text-white">{story.title}</h1><p className="story-archive-readable m-0 mt-2 whitespace-pre-wrap text-sm leading-6 text-white/80">{story.background}</p></header>
          <div className="grid gap-10">
            {archiveDays.map((day) => (
              <section key={day.key} data-testid="story-archive-day">
                <h2 className="story-archive-readable m-0 text-2xl font-semibold text-white">{day.label}</h2>
                <div className="mt-5 grid gap-7">
                  {day.periods.map((period) => (
                    <section key={`${day.key}:${period.timeBand}`} data-testid="story-archive-period">
                      <h3 className="story-archive-readable m-0 border-b border-white/20 pb-2 text-sm font-semibold tracking-[0.16em] text-white/80">{period.timeBand}</h3>
                      <ol className="m-0 mt-3 grid list-none gap-3">
                        {period.entries.map((entry) => (
                          <li className={`rounded-md border-l-2 px-4 py-3 ${entry.kind === "player" ? "border-[#A7D4E8] bg-white/10" : entry.kind === "dialogue" ? "border-[#F4C29F] bg-white/5" : "border-dashed border-white/35 bg-transparent"}`} data-story-entry-kind={entry.kind} key={entry.id} ref={entry.id === lastEntryId ? latestEntryRef : undefined}>
                            <p className="story-archive-readable m-0 mb-1 text-xs font-medium tracking-wide text-white/75">{entry.label}</p>
                            <p className="story-archive-readable m-0 whitespace-pre-wrap text-base leading-7 text-white">{entry.text}</p>
                          </li>
                        ))}
                      </ol>
                    </section>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </main>
        {error ? <div className="fixed bottom-5 left-1/2 -translate-x-1/2 rounded-md bg-[#793F36] px-4 py-2 text-sm text-white shadow-lg" role="alert">{error}</div> : null}
        </div>
      </div>
    </section>
  );
}
