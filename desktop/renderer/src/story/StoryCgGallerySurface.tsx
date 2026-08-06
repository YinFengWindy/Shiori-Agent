import { ArrowClockwise, ArrowLeft, ImageBroken, X } from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import type { StoryCgGallery, StoryResource } from "./types";
import { StorySurface } from "./StorySurface";
import { toFileUrl } from "../shared/format";
import type { StoryMenuBackground } from "./useStoryMenuBackground";
import { getStoryResourceErrorMessage } from "./selectors";

type StoryCgGallerySurfaceProps = {
  stories: StoryCgGallery[];
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  busy: boolean;
  error: string;
  onRetry: (storyId: string, resourceId: string) => void;
  onBack: () => void;
};

function resourceLabel(resource: StoryResource, index: number) {
  if (resource.kind === "background") return "开场背景";
  return `CG ${index + 1}`;
}

/** Renders the main-menu Story CG collection, grouped by Story. */
export function StoryCgGallerySurface({ stories, background, sharedBackdrop = false, busy, error, onRetry, onBack }: StoryCgGallerySurfaceProps) {
  const [selectedStoryId, setSelectedStoryId] = useState(stories[0]?.storyId ?? "");
  const [preview, setPreview] = useState<StoryResource | null>(null);
  const selectedStory = useMemo(
    () => stories.find((story) => story.storyId === selectedStoryId) ?? stories[0] ?? null,
    [selectedStoryId, stories],
  );

  return (
    <StorySurface background={background} sharedBackdrop={sharedBackdrop} dataTestId="story-cg-gallery" panelTestId="story-cg-gallery-panel" contentClassName="overflow-hidden">
      <header className="flex items-center gap-4 border-b border-[#DDA9BE]/65 px-[clamp(18px,4vw,40px)] py-5">
        <button className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-[#8F355C] transition-colors hover:text-[#7A2356] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0]" type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}>
          <ArrowLeft className="h-5 w-5" weight="bold" />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="m-0 font-serif text-2xl font-semibold italic text-[#7A2356]">CG 鉴赏</h1>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <nav className="min-h-0 overflow-y-auto border-b border-[#DDA9BE]/65 lg:border-b-0 lg:border-r lg:border-[#DDA9BE]/65" aria-label="故事 CG 集">
          {busy && !stories.length ? <p className="m-0 px-5 py-5 text-sm text-[#8B6676]">正在读取 CG 集</p> : stories.length ? stories.map((story) => {
            const active = selectedStory?.storyId === story.storyId;
            return (
              <button key={story.storyId} className={`flex w-full items-center justify-between gap-3 border-b border-[#DDA9BE]/55 px-5 py-4 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#E5A9C0] ${active ? "bg-[#7A2356]/10 text-[#7A2356]" : "text-[#765667] hover:bg-white/55"}`} type="button" onClick={() => { setSelectedStoryId(story.storyId); setPreview(null); }}>
                <strong className="block min-w-0 truncate font-serif text-base">{story.title}</strong>
              </button>
            );
          }) : <p className="m-0 px-5 py-5 text-sm text-[#8B6676]">还没有故事 CG</p>}
        </nav>

        <main className="min-h-0 overflow-y-auto px-[clamp(18px,4vw,40px)] py-7">
          <div className="mx-auto w-full max-w-5xl">
            {selectedStory ? <>
              <div className="flex items-baseline border-b border-[#DDA9BE]/65 pb-4">
                <h2 className="m-0 font-serif text-xl font-semibold italic text-[#7A2356]">{selectedStory.title}</h2>
              </div>
              {selectedStory.items.length ? <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {selectedStory.items.map((resource, index) => {
                  const canPreview = resource.status === "ready" && Boolean(resource.path);
                  const resourceErrorMessage = resource.status === "failed" ? getStoryResourceErrorMessage(resource.errorCode) : "";
                  return <figure key={resource.id} className="m-0 overflow-hidden border border-[#DDA9BE]/55 bg-[#FFF8FC]/55">
                    <button className="group relative aspect-video w-full overflow-hidden bg-[#5E2841]/10 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#E5A9C0]" type="button" disabled={busy || !canPreview} onClick={() => canPreview ? setPreview(resource) : undefined}>
                      {canPreview ? <img className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" src={toFileUrl(resource.path || "")} alt={`${selectedStory.title} ${resourceLabel(resource, index)}`} /> : resource.status === "generating" ? <span className="grid h-full place-items-center gap-2 text-sm text-[#8B6676]">正在生成</span> : <span className="grid h-full place-items-center text-[#A23E69]" data-testid="story-cg-resource-failed" role="img" aria-label={resourceErrorMessage} title={resource.errorCode || resourceErrorMessage}><ImageBroken className="h-8 w-8" weight="duotone" /></span>}
                      {resource.status === "generating" ? <span className="absolute inset-x-0 bottom-0 bg-[#4A2738]/75 px-3 py-2 text-xs text-white">正在生成</span> : null}
                    </button>
                    <figcaption className="flex items-center justify-between gap-3 border-t border-[#DDA9BE]/45 px-3 py-2 text-xs text-[#765667]">
                      <span>{resourceLabel(resource, index)}</span>
                      {resource.status === "failed" ? <span className="inline-flex min-w-0 items-center gap-2"><span className="truncate text-[#A23E69]" title={resource.errorCode || resourceErrorMessage}>{resourceErrorMessage}</span><button className="inline-flex shrink-0 items-center gap-1 text-[#A23E69] hover:text-[#7A2356] focus:outline-none focus-visible:underline" type="button" disabled={busy} onClick={() => onRetry(selectedStory.storyId, resource.id)}><ArrowClockwise weight="bold" />重试</button></span> : null}
                    </figcaption>
                  </figure>;
                })}
              </div> : <p className="m-0 py-8 text-sm text-[#8B6676]">这个故事还没有 CG</p>}
            </> : <div className="grid min-h-64 place-items-center text-sm text-[#8B6676]">还没有故事 CG</div>}
            {error ? <div className="mt-6 border border-[#D58A9F] bg-[#FFF0F4] px-3 py-2 text-sm text-[#9A365D]" role="alert">{error}</div> : null}
          </div>
        </main>
      </div>

      {preview ? <div className="fixed inset-0 z-40 grid place-items-center bg-[#1D1520]/80 p-6 backdrop-blur-md" role="dialog" aria-modal="true" aria-label="CG 预览">
        <button className="absolute right-5 top-5 grid h-10 w-10 place-items-center rounded-md text-white/80 transition-colors hover:bg-white/10 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70" type="button" aria-label="关闭 CG 预览" title="关闭 CG 预览" onClick={() => setPreview(null)}><X className="h-6 w-6" weight="bold" /></button>
        <img className="max-h-full max-w-full object-contain shadow-[0_18px_70px_rgba(0,0,0,0.5)]" src={toFileUrl(preview.path || "")} alt="CG 预览" />
      </div> : null}
    </StorySurface>
  );
}
