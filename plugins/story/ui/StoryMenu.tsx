import { StoryError } from "./StoryError";
import { ArrowLeft, Check, ImageSquare, PencilSimple, Plus, Trash, X } from "@phosphor-icons/react";
import { motion } from "motion/react";
import { useState } from "react";
import { usePluginHostServices } from "@yinfengwindy/shiori-sdk";
import type { StorySummary } from "./types";
import { describeStoryFailure } from "./storyFailure";
import { useStoryReducedMotion } from "./storyPreferences";
import { formatStoryDate } from "./storyTime";
import { StorySurface } from "./StorySurface";
import { storyEmptyTextClass, storyGutterClass, storyIconButtonClass, storyInputClass, storyPageHeaderClass, storyPageTitleClass, storyPrimaryButtonClass } from "./storyStyles";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type LauncherActions = {
  busy: boolean;
  reducedMotion: boolean;
  onCreateStory: () => void;
  onOpenLoad: () => void;
  onOpenCg: () => void;
  onOpenSettings: () => void;
  onExit: () => void;
};

type StoryLoadListProps = {
  busy: boolean;
  stories: StorySummary[];
  background?: StoryMenuBackground;
  sharedBackdrop?: boolean;
  error?: string;
  errorDetail?: string;
  onBack: () => void;
  onCreateStory: () => void;
  onLoadStory: (storyId: string) => void;
  onRenameStory: (storyId: string, title: string) => Promise<void>;
  onDeleteStory: (storyId: string) => Promise<void>;
};

type StoryFailure = ReturnType<typeof describeStoryFailure>;

const commandClass = "story-command-text flex min-h-16 w-full flex-col items-end justify-center gap-1 border-b border-[color:var(--story-command-line)] py-3 text-right font-serif text-[color:var(--story-wine)] transition-[color,border-color] hover:border-[color:var(--story-command-line-hover)] hover:text-[color:var(--story-wine-hover)] disabled:cursor-default disabled:opacity-40";
const panelTransition = { duration: 0.28, ease: "easeOut" } as const;

/** Newest saves first; the catalog lists them in creation order. */
function sortStoriesByRecency(stories: StorySummary[]) {
  return [...stories].sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

/** Renders the Story launch commands as a cinematic, keyboard-accessible rail. */
export function StoryMainMenu({ busy, reducedMotion, onCreateStory, onOpenLoad, onOpenCg, onOpenSettings, onExit }: LauncherActions) {
  const commands = [
    { label: "新的故事", ornament: "NEW STORY", onSelect: onCreateStory },
    { label: "读取存档", ornament: "LOAD", onSelect: onOpenLoad },
    { label: "CG 鉴赏", ornament: "GALLERY", onSelect: onOpenCg },
    { label: "设置", ornament: "SETTINGS", onSelect: onOpenSettings },
    { label: "离开", ornament: "EXIT", onSelect: onExit },
  ];
  return (
    <motion.nav aria-label="故事菜单" className="grid gap-2" data-testid="story-launcher-command-rail" initial={{ opacity: 0, x: reducedMotion ? 0 : 28 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: reducedMotion ? 0 : 20 }} transition={panelTransition}>
      {commands.map((command) => (
        <motion.button key={command.ornament} className={commandClass} type="button" disabled={busy} whileHover={reducedMotion ? undefined : { x: -8 }} whileTap={reducedMotion ? undefined : { scale: 0.98 }} onClick={command.onSelect}>
          <span className="text-[1.6rem] font-semibold leading-none">{command.label}</span>
          <span aria-hidden="true" className="text-[0.68rem] italic leading-none tracking-[0.32em] opacity-70">{command.ornament}</span>
        </motion.button>
      ))}
    </motion.nav>
  );
}

function StoryCover({ story }: { story: StorySummary }) {
  const host = usePluginHostServices();
  return <span className="relative grid aspect-video w-28 shrink-0 place-items-center overflow-hidden rounded-sm border border-[color:var(--story-line-soft)] bg-[color:var(--story-paper-selected)] text-[color:var(--story-rose)]">
    {story.coverPath ? <img className="h-full w-full object-cover" src={host.assets.url(story.coverPath)} alt="" /> : <ImageSquare className="h-6 w-6" weight="duotone" aria-hidden="true" />}
  </span>;
}

type StoryLoadRowProps = {
  story: StorySummary;
  busy: boolean;
  reducedMotion: boolean;
  onLoad: () => void;
  onRename: (title: string) => Promise<void>;
  onRequestDelete: () => void;
};

/** One save: loads on click, renames inline, and asks before deleting. */
function StoryLoadRow({ story, busy, reducedMotion, onLoad, onRename, onRequestDelete }: StoryLoadRowProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<StoryFailure | null>(null);
  const sceneLabel = (story.currentScene.name ?? "").trim() || "未命名场景";
  const meta = [story.roleName, formatStoryDate(story.currentStoryDate), story.currentTimeBand, sceneLabel].filter(Boolean).join(" · ");

  async function commitRename() {
    if (draft === null || saving) return;
    const title = draft.trim();
    if (!title || title === story.title) {
      setDraft(null);
      return;
    }
    setSaving(true);
    setFailure(null);
    try {
      await onRename(title);
      setDraft(null);
    } catch (cause) {
      setFailure(describeStoryFailure(cause, "重命名失败，请重试"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="border-b border-[color:var(--story-line)] bg-[color:var(--story-paper-soft)] transition-colors hover:bg-[color:var(--story-paper-strong)]">
      <div className="flex min-h-20 items-center gap-3 px-3 py-3">
        {draft === null ? (
          <motion.button className="flex min-w-0 flex-1 items-center gap-4 rounded-sm text-left disabled:opacity-40" type="button" disabled={busy} whileTap={reducedMotion ? undefined : { scale: 0.99 }} onClick={onLoad}>
            <StoryCover story={story} />
            <span className="min-w-0 flex-1">
              <strong className="block truncate font-serif text-base text-[color:var(--story-ink-strong)]">{story.title}</strong>
              <span className="mt-1 block truncate text-xs text-[color:var(--story-ink-muted)]">{meta}</span>
            </span>
          </motion.button>
        ) : (
          <form className="flex min-w-0 flex-1 items-center gap-4" onSubmit={(event) => { event.preventDefault(); void commitRename(); }}>
            <StoryCover story={story} />
            <input className={storyInputClass} aria-label="剧情名称" autoFocus value={draft} disabled={saving} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); setDraft(null); setFailure(null); } }} />
            <button className={storyIconButtonClass} type="submit" aria-label="保存名称" title="保存名称" disabled={saving || !draft.trim()}><Check className="h-5 w-5" weight="bold" /></button>
            <button className={storyIconButtonClass} type="button" aria-label="取消重命名" title="取消重命名" disabled={saving} onClick={() => { setDraft(null); setFailure(null); }}><X className="h-5 w-5" weight="bold" /></button>
          </form>
        )}
        {draft === null ? <div className="flex shrink-0 gap-1">
          <button className={storyIconButtonClass} type="button" aria-label={`重命名「${story.title}」`} title="重命名" disabled={busy} onClick={() => setDraft(story.title)}><PencilSimple className="h-5 w-5" /></button>
          <button className={`${storyIconButtonClass} hover:text-[color:var(--story-danger)]`} type="button" aria-label={`删除「${story.title}」`} title="删除" disabled={busy} onClick={onRequestDelete}><Trash className="h-5 w-5" /></button>
        </div> : null}
      </div>
      {failure ? <StoryError className="mx-3 mb-3" message={failure.error} detail={failure.errorDetail} /> : null}
    </li>
  );
}

/** Renders saved Stories, newest first, with load, rename and delete. */
export function StoryLoadList({ stories, busy, background, sharedBackdrop = false, error = "", errorDetail, onBack, onCreateStory, onLoadStory, onRenameStory, onDeleteStory }: StoryLoadListProps) {
  const reducedMotion = useStoryReducedMotion();
  const host = usePluginHostServices();
  const [pendingDelete, setPendingDelete] = useState<StorySummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteFailure, setDeleteFailure] = useState<StoryFailure | null>(null);
  const orderedStories = sortStoriesByRecency(stories);

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteFailure(null);
    try {
      await onDeleteStory(pendingDelete.storyId);
      setPendingDelete(null);
    } catch (cause) {
      setDeleteFailure(describeStoryFailure(cause, "删除失败，请重试"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <StorySurface background={background} sharedBackdrop={sharedBackdrop} dataTestId="story-load" panelTestId="story-load-panel">
      <header className={storyPageHeaderClass}>
        <button className={storyIconButtonClass} type="button" aria-label="返回剧情主菜单" title="返回剧情主菜单" onClick={onBack}>
          <ArrowLeft className="h-5 w-5" weight="bold" />
        </button>
        <h1 className={`${storyPageTitleClass} min-w-0 flex-1`}>读取存档</h1>
      </header>

      <div className={`min-h-0 flex-1 overflow-y-auto py-7 ${storyGutterClass}`}>
        <div className="mx-auto w-full max-w-3xl">
          {orderedStories.length ? (
            <ul className="m-0 grid list-none border-t border-[color:var(--story-line)] p-0" data-testid="story-load-list" aria-label="已保存剧情">
              {orderedStories.map((story) => (
                <StoryLoadRow key={story.storyId} story={story} busy={busy || deleting} reducedMotion={reducedMotion} onLoad={() => onLoadStory(story.storyId)} onRename={(title) => onRenameStory(story.storyId, title)} onRequestDelete={() => { setDeleteFailure(null); setPendingDelete(story); }} />
              ))}
            </ul>
          ) : <div className="grid justify-items-start gap-4">
            <p className={`${storyEmptyTextClass} w-full`}>暂无已保存的剧情</p>
            <button className={storyPrimaryButtonClass} type="button" disabled={busy} onClick={onCreateStory}><Plus className="h-4 w-4" weight="bold" aria-hidden="true" />新的故事</button>
          </div>}
          {error ? <StoryError className="mt-5" message={error} detail={errorDetail} /> : null}
        </div>
      </div>

      <host.ui.ConfirmDialog
        open={pendingDelete !== null}
        title="删除剧情"
        description={pendingDelete ? `「${pendingDelete.title}」的剧情记录和 CG 会一起删除，无法恢复。` : ""}
        confirmLabel="删除"
        busyLabel="正在删除"
        destructive
        persona="destructive"
        busy={deleting}
        error={deleteFailure?.error}
        onClose={() => { if (!deleting) setPendingDelete(null); }}
        onConfirm={() => { void confirmDelete(); }}
      />
    </StorySurface>
  );
}
