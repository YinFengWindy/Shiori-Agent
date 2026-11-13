import { StoryError } from "./StoryError";
import { ArrowClockwise, ArrowLeft, CaretLeft, CaretRight, ImageBroken, X } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { cx, useLatestRef, usePluginHostServices } from "@yinfengwindy/shiori-sdk";
import type { StoryCgGallery, StoryResource } from "./types";
import { StorySurface } from "./StorySurface";
import { useStoryReducedMotion } from "./storyPreferences";
import { storyEmptyTextClass, storyGutterClass, storyIconButtonClass, storyPageHeaderClass, storyPageTitleClass, storySectionTitleClass } from "./storyStyles";
import type { StoryMenuBackground } from "./useStoryMenuBackground";
import { getStoryResourceErrorMessage } from "./selectors";

type StoryCgGallerySurfaceProps = {
  stories: StoryCgGallery[];
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  busy: boolean;
  error: string;
  errorDetail?: string;
  onRetry: (storyId: string, resourceId: string) => void;
  onBack: () => void;
};

const lightboxButtonClass = "grid h-11 w-11 place-items-center rounded-md text-[color:var(--story-stage-ink-muted)] transition-colors hover:bg-[color:var(--story-stage-glass-hover)] hover:text-[color:var(--story-stage-ink)] disabled:cursor-default disabled:opacity-30";

function resourceLabel(resource: StoryResource, index: number) {
  if (resource.kind === "background") return "开场背景";
  return `CG ${index + 1}`;
}

function isPreviewable(resource: StoryResource) {
  return resource.status === "ready" && Boolean(resource.path);
}

/** Renders the main-menu Story CG collection, grouped by Story, with a keyboard-navigable preview. */
export function StoryCgGallerySurface({ stories, background, sharedBackdrop = false, busy, error, errorDetail, onRetry, onBack }: StoryCgGallerySurfaceProps) {
  const [selectedStoryId, setSelectedStoryId] = useState(stories[0]?.storyId ?? "");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const previewTriggerRef = useRef<HTMLElement | null>(null);
  const reducedMotion = useStoryReducedMotion();
  const host = usePluginHostServices();
  const selectedStory = stories.find((story) => story.storyId === selectedStoryId) ?? stories[0] ?? null;
  const items = selectedStory?.items ?? [];
  const previewable = items.filter(isPreviewable);
  const previewIndex = previewable.findIndex((resource) => resource.id === previewId);
  const preview = previewIndex >= 0 ? previewable[previewIndex] : null;

  function closePreview() {
    setPreviewId(null);
    previewTriggerRef.current?.focus();
  }

  function stepPreview(offset: number) {
    const target = previewable[previewIndex + offset];
    if (target) setPreviewId(target.id);
  }

  const keyHandlerRef = useLatestRef((event: KeyboardEvent) => {
    if (event.key === "Escape") closePreview();
    else if (event.key === "ArrowLeft") stepPreview(-1);
    else if (event.key === "ArrowRight") stepPreview(1);
    else return;
    event.preventDefault();
  });
  const previewOpen = preview !== null;
  useEffect(() => {
    if (!previewOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => keyHandlerRef.current(event);
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [keyHandlerRef, previewOpen]);

  return (
    <StorySurface background={background} sharedBackdrop={sharedBackdrop} dataTestId="story-cg-gallery" panelTestId="story-cg-gallery-panel" contentClassName="overflow-hidden">
      <header className={storyPageHeaderClass}>
        <button className={storyIconButtonClass} type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}>
          <ArrowLeft className="h-5 w-5" weight="bold" />
        </button>
        <h1 className={`${storyPageTitleClass} min-w-0 flex-1`}>CG 鉴赏</h1>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <nav className="min-h-0 overflow-y-auto border-b border-[color:var(--story-line)] lg:border-b-0 lg:border-r" aria-label="故事 CG 集">
          {busy && !stories.length ? <p className="m-0 px-5 py-5 text-sm text-[color:var(--story-ink-muted)]">正在读取 CG 集</p> : stories.length ? stories.map((story) => {
            const active = selectedStory?.storyId === story.storyId;
            const readyCount = story.items.filter(isPreviewable).length;
            return (
              <button key={story.storyId} className={cx("flex w-full items-center justify-between gap-3 border-b border-[color:var(--story-line-soft)] px-5 py-4 text-left transition-colors", active ? "bg-[color:var(--story-paper-selected)] text-[color:var(--story-wine)]" : "text-[color:var(--story-ink)] hover:bg-[color:var(--story-paper-strong)]")} type="button" aria-current={active ? "true" : undefined} onClick={() => { setSelectedStoryId(story.storyId); setPreviewId(null); }}>
                <strong className="block min-w-0 truncate font-serif text-base">{story.title}</strong>
                <span className="shrink-0 text-xs tabular-nums text-[color:var(--story-ink-muted)]">{readyCount}</span>
              </button>
            );
          }) : <p className="m-0 px-5 py-5 text-sm text-[color:var(--story-ink-muted)]">还没有故事 CG</p>}
        </nav>

        <main className={`min-h-0 overflow-y-auto py-7 ${storyGutterClass}`}>
          <div className="mx-auto w-full max-w-5xl">
            {selectedStory ? <>
              <div className="flex items-baseline border-b border-[color:var(--story-line)] pb-4">
                <h2 className={storySectionTitleClass}>{selectedStory.title}</h2>
              </div>
              {items.length ? <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {items.map((resource, index) => {
                  const canPreview = isPreviewable(resource);
                  const resourceErrorMessage = resource.status === "failed" ? getStoryResourceErrorMessage(resource.errorCode) : "";
                  return <figure key={resource.id} className="m-0 overflow-hidden border border-[color:var(--story-line-soft)] bg-[color:var(--story-paper-soft)]">
                    <button className="group relative aspect-video w-full overflow-hidden bg-[color:var(--story-paper-selected)] text-left" type="button" aria-label={canPreview ? `查看${resourceLabel(resource, index)}` : undefined} disabled={busy || !canPreview} onClick={(event) => { if (!canPreview) return; previewTriggerRef.current = event.currentTarget; setPreviewId(resource.id); }}>
                      {canPreview ? <img className="h-full w-full object-cover transition duration-500 motion-safe:group-hover:scale-[1.03]" src={host.assets.url(resource.path || "")} alt={`${selectedStory.title} ${resourceLabel(resource, index)}`} /> : resource.status === "generating" ? <span className="grid h-full place-items-center gap-2 text-sm text-[color:var(--story-ink-muted)]">正在生成</span> : <span className="grid h-full place-items-center text-[color:var(--story-danger)]" data-testid="story-cg-resource-failed" role="img" aria-label={resourceErrorMessage} title={resource.errorCode || resourceErrorMessage}><ImageBroken className="h-8 w-8" weight="duotone" /></span>}
                    </button>
                    <figcaption className="flex items-center justify-between gap-3 border-t border-[color:var(--story-line-soft)] px-3 py-2 text-xs text-[color:var(--story-ink)]">
                      <span>{resourceLabel(resource, index)}</span>
                      {resource.status === "failed" ? <span className="inline-flex min-w-0 items-center gap-2"><span className="truncate text-[color:var(--story-danger)]" title={resource.errorCode || resourceErrorMessage}>{resourceErrorMessage}</span><button className="inline-flex shrink-0 items-center gap-1 rounded-sm text-[color:var(--story-danger)] hover:text-[color:var(--story-wine)]" type="button" disabled={busy} onClick={() => onRetry(selectedStory.storyId, resource.id)}><ArrowClockwise weight="bold" />重试</button></span> : null}
                    </figcaption>
                  </figure>;
                })}
              </div> : <p className={cx(storyEmptyTextClass, "border-b-0")}>这个故事还没有 CG</p>}
            </> : <div className="grid min-h-64 place-items-center text-sm text-[color:var(--story-ink-muted)]">还没有故事 CG</div>}
            {error ? <StoryError className="mt-5" message={error} detail={errorDetail} /> : null}
          </div>
        </main>
      </div>

      <AnimatePresence initial={false}>
        {preview ? <motion.div
          key="story-cg-preview"
          className="fixed inset-0 z-40 grid grid-rows-[minmax(0,1fr)_auto] place-items-center gap-3 bg-[color:var(--story-lightbox)] p-6 backdrop-blur-md"
          role="dialog"
          aria-modal="true"
          aria-label="CG 预览"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reducedMotion ? 0.12 : 0.18, ease: "easeOut" }}
          onClick={(event) => { if (event.target === event.currentTarget) closePreview(); }}
        >
          <button className={cx(lightboxButtonClass, "absolute right-5 top-5")} type="button" aria-label="关闭 CG 预览" title="关闭 CG 预览（Esc）" autoFocus onClick={closePreview}><X className="h-6 w-6" weight="bold" /></button>
          <button className={cx(lightboxButtonClass, "absolute left-5 top-1/2 -translate-y-1/2")} type="button" aria-label="上一张" title="上一张（←）" disabled={previewIndex <= 0} onClick={() => stepPreview(-1)}><CaretLeft className="h-6 w-6" weight="bold" /></button>
          <button className={cx(lightboxButtonClass, "absolute right-5 top-1/2 -translate-y-1/2")} type="button" aria-label="下一张" title="下一张（→）" disabled={previewIndex >= previewable.length - 1} onClick={() => stepPreview(1)}><CaretRight className="h-6 w-6" weight="bold" /></button>
          <AnimatePresence initial={false} mode="wait">
            <motion.img
              key={preview.id}
              className="max-h-full max-w-[calc(100%-8rem)] object-contain shadow-[var(--story-shadow-lightbox)]"
              src={host.assets.url(preview.path || "")}
              alt={`${selectedStory?.title ?? ""} ${resourceLabel(preview, items.indexOf(preview))}`}
              initial={{ opacity: 0, transform: reducedMotion ? "scale(1)" : "scale(0.97)" }}
              animate={{ opacity: 1, transform: "scale(1)" }}
              exit={{ opacity: 0, transform: reducedMotion ? "scale(1)" : "scale(0.97)" }}
              transition={{ duration: reducedMotion ? 0.12 : 0.2, ease: "easeOut" }}
            />
          </AnimatePresence>
          <p className="m-0 text-sm tabular-nums text-[color:var(--story-stage-ink-muted)]" aria-live="polite">{resourceLabel(preview, items.indexOf(preview))} · {previewIndex + 1} / {previewable.length}</p>
        </motion.div> : null}
      </AnimatePresence>
    </StorySurface>
  );
}
