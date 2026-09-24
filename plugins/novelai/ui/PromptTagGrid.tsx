import { DotsThree, PencilSimple, Plus, Trash } from "@phosphor-icons/react";
import { toFileUrl } from "../../../apps/desktop/renderer/src/shared/format";
import { badgeClass, compactButtonSizeClass, compactPressableClass, cx, primaryButtonSurfaceClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { ActionMenu } from "../../../apps/desktop/renderer/src/shared/ui/ActionMenu";
import { PetalIcon, SparkleIcon } from "../../../apps/desktop/renderer/src/shared/ui/icons";
import type { PromptTagEntry } from "./types";

type PromptTagGridProps = {
  entries: PromptTagEntry[];
  loaded: boolean;
  onOpen: (entry: PromptTagEntry) => void;
  onCreate: () => void;
  onDelete: (entry: PromptTagEntry) => void;
};

function NewEntryButton({ onCreate }: { onCreate: () => void }) {
  return (
    <button className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)} type="button" onClick={onCreate}>
      <Plus className="h-4 w-4" weight="bold" aria-hidden="true" />
      新建提示词
    </button>
  );
}

/** An empty library: the brand motif and the one action that fills it. */
function PromptTagEmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="motion-fade-enter grid justify-items-center gap-4 py-24 text-center" data-testid="prompt-tag-empty">
      <span className="relative grid h-20 w-20 place-items-center rounded-full border border-white/80 bg-white/70 text-accent shadow-soft">
        <SparkleIcon className="h-8 w-8" />
        <span className="absolute -bottom-1 -right-1 text-lavender"><PetalIcon className="h-5 w-5" /></span>
      </span>
      <span className="font-display text-title text-ink">还没有提示词</span>
      <NewEntryButton onCreate={onCreate} />
    </div>
  );
}

function PromptTagCard({ entry, onOpen, onDelete }: { entry: PromptTagEntry; onOpen: () => void; onDelete: () => void }) {
  return (
    <article className="group relative isolate aspect-[4/5] overflow-hidden rounded-lg border border-line-soft bg-surface shadow-soft transition-[box-shadow] duration-base ease-out-soft hover:shadow-pop focus-within:shadow-pop">
      {entry.image_path ? (
        <>
          <img className="absolute inset-0 h-full w-full object-cover object-top" src={toFileUrl(entry.image_path)} alt="" />
          <div className="absolute inset-x-0 bottom-0 h-3/5 bg-gradient-to-t from-white/95 via-white/75 to-transparent" aria-hidden="true" />
        </>
      ) : (
        <div className="absolute inset-0 grid place-items-center bg-gradient-accent-soft text-accent" aria-hidden="true">
          <SparkleIcon className="h-10 w-10 opacity-70" />
        </div>
      )}
      <button className="absolute inset-0 z-[1] rounded-lg" type="button" aria-label={`打开 ${entry.name}`} title={entry.name} onClick={onOpen} />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[2] grid gap-1.5 p-4">
        <h3 className="m-0 truncate font-display text-title-sm text-ink">{entry.name}</h3>
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span className={cx(badgeClass, "bg-white/80 text-ink-secondary")}>{entry.category}</span>
          {!entry.enabled ? <span className={cx(badgeClass, "bg-surface-soft text-ink-muted")}>已停用</span> : null}
        </div>
      </div>
      <div className="absolute right-3 top-3 z-[3]">
        <ActionMenu
          label={`${entry.name} 的更多操作`}
          triggerClassName={cx(compactPressableClass, "surface-glass-strong grid h-8 w-8 place-items-center rounded-full text-ink-secondary hover:text-ink")}
          items={[
            { id: "edit", label: "编辑", icon: <PencilSimple className="h-4 w-4" />, onSelect: onOpen },
            { id: "delete", label: "删除", icon: <Trash className="h-4 w-4" />, danger: true, separated: true, onSelect: onDelete },
          ]}
        >
          <DotsThree className="h-5 w-5" weight="bold" aria-hidden="true" />
        </ActionMenu>
      </div>
    </article>
  );
}

/** The library list: a header with the count and 新建, then cards, or the brand empty state. */
export function PromptTagGrid({ entries, loaded, onOpen, onCreate, onDelete }: PromptTagGridProps) {
  if (loaded && !entries.length) return <PromptTagEmptyState onCreate={onCreate} />;
  return (
    <div className="grid gap-5">
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-baseline gap-2">
          <h2 className="m-0 font-display text-headline text-ink">提示词库</h2>
          {loaded ? <span className="text-body-sm tabular-nums text-ink-muted">{entries.length} 条</span> : null}
        </div>
        <NewEntryButton onCreate={onCreate} />
      </header>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(190px,1fr))] gap-4">
        {entries.map((entry) => (
          <PromptTagCard key={entry.id} entry={entry} onOpen={() => onOpen(entry)} onDelete={() => onDelete(entry)} />
        ))}
      </div>
    </div>
  );
}
