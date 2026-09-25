import { toFileUrl } from "../../../apps/desktop/renderer/src/shared/format";
import { cx, pressableClass } from "../../../apps/desktop/renderer/src/shared/styles";
import type { ImageHistoryRecord } from "./types";

type ImageFilmstripProps = {
  items: ImageHistoryRecord[];
  selectedRecordId: string;
  /** The just-generated record, which enters with the reveal curve. */
  revealRecordId: string;
  onSelect: (recordId: string) => void;
};

const timeFormat = new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });

function formatCreatedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : timeFormat.format(date);
}

/** This role's recent generations as a strip under the canvas; the selected one is on the stage. */
export function ImageFilmstrip({ items, selectedRecordId, revealRecordId, onSelect }: ImageFilmstripProps) {
  if (!items.length) return null;
  const activeId = items.some((item) => item.id === selectedRecordId) ? selectedRecordId : items[0].id;
  return (
    <nav className="surface-glass flex min-w-0 items-center gap-3 rounded-lg py-2 pl-3.5 pr-2" aria-label="历史作品" data-testid="novelai-filmstrip">
      <span className="grid shrink-0 gap-0.5">
        <span className="text-body-sm font-medium text-ink">历史</span>
        <span className="text-caption tabular-nums text-ink-muted">{items.length} 张</span>
      </span>
      <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto px-0.5 py-1">
        {items.map((item) => {
          const selected = item.id === activeId;
          const preview = item.output_paths[0] ?? "";
          const time = formatCreatedAt(item.created_at);
          return (
            <button
              key={item.id}
              className={cx(
                pressableClass,
                "h-16 w-16 shrink-0 overflow-hidden rounded-md border-2 bg-surface-soft",
                selected ? "border-accent shadow-soft" : "border-white/80 opacity-80 hover:opacity-100",
                item.id === revealRecordId && "nai-thumb-enter",
              )}
              type="button"
              aria-pressed={selected}
              aria-label={time ? `${time} 的作品` : "历史作品"}
              title={item.prompt}
              onClick={() => onSelect(item.id)}
            >
              {preview ? <img className="h-full w-full object-cover" src={toFileUrl(preview)} alt="" /> : null}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
