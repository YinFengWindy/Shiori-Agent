import { toFileUrl } from "../shared/format";
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
    <section className="flex h-full min-h-0 flex-col gap-3 rounded-[20px] bg-white p-3">
      <div className="flex items-center justify-between px-1 pt-1">
        <div className="text-sm font-medium text-[#20242A]">History</div>
      </div>
      <div className="scrollbar-soft flex-1 min-h-0 overflow-y-auto pr-1">
        <div className="grid content-start gap-2">
        {items.length ? items.map((item) => {
          const previewPath = item.output_paths[0] ?? "";
          const selected = item.id === selectedRecordId;
          return (
            <button
              key={item.id}
              className={cx(
                "rounded-[16px] border p-2 text-left transition focus:outline-none",
                selected ? "border-black bg-white shadow-[0_8px_24px_rgba(15,23,42,0.08)]" : "border-transparent bg-white/60 hover:bg-white/85",
              )}
              type="button"
              onClick={() => onSelect(item)}
            >
              <div className="aspect-square w-full overflow-hidden rounded-[14px] bg-[#F1F5F9]">
                {previewPath ? (
                  <img className="h-full w-full object-contain" src={toFileUrl(previewPath)} alt="history preview" />
                ) : null}
              </div>
            </button>
          );
        }) : (
          <div className="rounded-[14px] bg-white px-3 py-5 text-center text-[12px] text-[#737781] shadow-[0_6px_18px_rgba(15,23,42,0.04)]">
            暂无绘图记录
          </div>
        )}
        </div>
      </div>
    </section>
  );
}
