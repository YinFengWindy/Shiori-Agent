import { formatTimestamp, toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import type { ImageHistoryRecord } from "./types";

type ImageHistoryPanelProps = {
  items: ImageHistoryRecord[];
  selectedRecordId: string;
  onSelect: (record: ImageHistoryRecord) => void;
};

export function ImageHistoryPanel({
  items,
  selectedRecordId,
  onSelect,
}: ImageHistoryPanelProps) {
  return (
    <section className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-3 rounded-[24px] border border-[#E4EAF0] bg-[#FBFCFE] p-4">
      <div className="text-sm font-semibold text-[#20242A]">历史</div>
      <div className="scrollbar-soft grid min-h-0 content-start gap-2 overflow-y-auto pr-1">
        {items.length ? items.map((item) => {
          const previewPath = item.output_paths[0] ?? "";
          const selected = item.id === selectedRecordId;
          return (
            <button
              key={item.id}
              className={cx(
                "grid grid-cols-[72px_minmax(0,1fr)] gap-3 rounded-[18px] border p-2 text-left transition",
                selected ? "border-[#272536] bg-white shadow-[0_8px_24px_rgba(15,23,42,0.08)]" : "border-[#E4EAF0] bg-white/80 hover:border-[#9AA3B2]",
              )}
              type="button"
              onClick={() => onSelect(item)}
            >
              <div className="h-[72px] w-[72px] overflow-hidden rounded-[12px] bg-[#F1F5F9]">
                {previewPath ? (
                  <img className="h-full w-full object-cover" src={toFileUrl(previewPath)} alt="history preview" />
                ) : null}
              </div>
              <div className="grid min-w-0 gap-1">
                <div className="truncate text-[12px] font-medium text-[#20242A]">{item.prompt}</div>
                <div className="text-[11px] text-[#6B7280]">{formatTimestamp(item.created_at)}</div>
                <div className="text-[11px] text-[#6B7280]">{`${item.mode} · ${item.width}×${item.height}`}</div>
                <div className="text-[11px] text-[#6B7280]">{`seed ${item.seed ?? "-"}`}</div>
              </div>
            </button>
          );
        }) : (
          <div className="rounded-[18px] border border-dashed border-[#D8DCE2] bg-white px-4 py-6 text-sm text-[#737781]">
            暂无记录
          </div>
        )}
      </div>
    </section>
  );
}
