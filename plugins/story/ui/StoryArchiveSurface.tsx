import { StoryError } from "./StoryError";
import { ArrowLeft } from "@phosphor-icons/react";
import { useEffect, useLayoutEffect, useRef } from "react";
import { cx, useLatestRef } from "@yinfengwindy/shiori-sdk";
import { DEFAULT_STORY_MENU_BACKGROUND } from "./StoryMenuScene";
import { buildStoryArchiveDays } from "./storyArchivePresentation";
import { storyIconButtonClass } from "./storyStyles";
import type { StoryDetails } from "./types";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StoryArchiveSurfaceProps = {
  story: StoryDetails;
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  error: string;
  errorDetail?: string;
  onReturnToGame: () => void;
};

const entryClass = {
  player: "border-[color:var(--story-entry-player-mark)] bg-[color:var(--story-entry-player)]",
  dialogue: "border-[color:var(--story-entry-dialogue-mark)] bg-[color:var(--story-entry-dialogue)]",
  narration: "border-dashed border-[color:var(--story-line-field)] bg-[color:var(--story-entry-narration)]",
} as const;

/** Renders the immutable Story beat history without exposing gameplay input controls. */
export function StoryArchiveSurface({ story, background = DEFAULT_STORY_MENU_BACKGROUND, sharedBackdrop = false, error, errorDetail, onReturnToGame }: StoryArchiveSurfaceProps) {
  const latestEntryRef = useRef<HTMLLIElement | null>(null);
  const returnRef = useLatestRef(onReturnToGame);
  const archiveDays = buildStoryArchiveDays(story);
  const lastEntryId = archiveDays.at(-1)?.periods.at(-1)?.entries.at(-1)?.id;

  useLayoutEffect(() => {
    latestEntryRef.current?.scrollIntoView({ block: "nearest" });
  }, [lastEntryId]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      event.preventDefault();
      returnRef.current();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [returnRef]);

  return (
    <section className={cx("relative h-full min-h-0 overflow-hidden text-[color:var(--story-ink)]", sharedBackdrop ? "bg-transparent" : "bg-[color:var(--story-night)]")} data-testid="story-archive-surface">
      {sharedBackdrop ? null : <div aria-hidden="true" className="absolute inset-0 bg-cover bg-center bg-no-repeat" data-testid="story-archive-backdrop" style={{ backgroundImage: `url(${background.url})` }} />}
      <div aria-hidden="true" className={cx("story-archive-reading-layer absolute inset-0", !sharedBackdrop && "backdrop-blur-sm")} />
      <div className="relative z-10 grid h-full min-h-0 grid-rows-[minmax(0,1fr)]">
        <div className="pointer-events-none absolute right-5 top-5 z-10 flex gap-2">
          <button className={cx(storyIconButtonClass, "pointer-events-auto border border-[color:var(--story-line)] bg-[color:var(--story-paper)]")} type="button" aria-label="返回游戏页" title="返回游戏页（Esc）" onClick={onReturnToGame}><ArrowLeft /></button>
        </div>
        <div className="min-h-0 overflow-y-auto px-5 py-8">
          <main className="mx-auto grid max-w-3xl gap-8">
            <header className="border-b border-[color:var(--story-line)] pb-4"><p className="story-archive-readable m-0 text-xs text-[color:var(--story-ink-muted)]">剧情记录</p><h1 className="m-0 mt-1 font-serif text-2xl font-semibold text-[color:var(--story-wine)]">{story.title}</h1><p className="story-archive-readable m-0 mt-2 whitespace-pre-wrap text-sm leading-6 text-[color:var(--story-ink)]">{story.background}</p></header>
            <div className="grid gap-10">
              {archiveDays.map((day) => (
                <section key={day.key} data-testid="story-archive-day">
                  <h2 className="m-0 font-serif text-2xl font-semibold text-[color:var(--story-wine)]">{day.label}</h2>
                  <div className="mt-5 grid gap-7">
                    {day.periods.map((period) => (
                      <section key={`${day.key}:${period.timeBand}`} data-testid="story-archive-period">
                        <h3 className="story-archive-readable m-0 border-b border-[color:var(--story-line)] pb-2 text-sm font-semibold tracking-[0.16em] text-[color:var(--story-rose)]">{period.timeBand}</h3>
                        <ol className="m-0 mt-3 grid list-none gap-3 p-0">
                          {period.entries.map((entry) => (
                            <li className={cx("story-archive-entry rounded-md border-l-2 px-4 py-3", entryClass[entry.kind])} data-story-entry-kind={entry.kind} key={entry.id} ref={entry.id === lastEntryId ? latestEntryRef : undefined}>
                              <p className="story-archive-readable m-0 mb-1 text-xs font-medium tracking-wide text-[color:var(--story-ink-muted)]">{entry.label}</p>
                              <p className={cx("story-archive-readable m-0 whitespace-pre-wrap text-base leading-7 text-[color:var(--story-ink-strong)]", entry.kind === "narration" && "italic")}>{entry.text}</p>
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
          {error ? <StoryError className="fixed bottom-5 left-1/2 z-40 w-[min(32rem,calc(100%-2rem))] -translate-x-1/2" message={error} detail={errorDetail} /> : null}
        </div>
      </div>
    </section>
  );
}
