import { cx, ghostButtonClass } from "../shared/styles";

type RoleMoodBindingsPanelProps = {
  moodCatalog: string[];
  defaultMood: string;
  activeMood: string;
  activeMoodIllustrationPath: string;
  activeMoodIllustrationAbsPath: string;
  selectedAssetPath: string;
  onSelectMood: (mood: string) => void;
  onBindSelectedAsset: () => void;
  onClearMoodBinding: () => void;
};

/** Renders the role asset-side mood binding panel. */
export function RoleMoodBindingsPanel({
  moodCatalog,
  defaultMood,
  activeMood,
  activeMoodIllustrationPath,
  activeMoodIllustrationAbsPath,
  selectedAssetPath,
  onSelectMood,
  onBindSelectedAsset,
  onClearMoodBinding,
}: RoleMoodBindingsPanelProps) {
  return (
    <div className="flex h-full min-h-[420px] flex-col rounded-[24px] border border-[#E4EAF0] bg-[#FAFBFD] p-5">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-[#2A3440]">心情映射</div>
          <div className="mt-1 text-xs text-[#7A8593]">为当前角色的每个心情绑定一张差分立绘。</div>
        </div>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        {moodCatalog.map((mood) => (
          <button
            key={mood}
            className={cx(
              "rounded-full px-4 py-2 text-sm transition",
              activeMood === mood
                ? "bg-[#272536] text-white shadow-[0_6px_16px_rgba(39,37,54,0.18)]"
                : "border border-[#D8DFE7] bg-white text-[#5B6472] hover:text-[#272536]",
            )}
            type="button"
            onClick={() => onSelectMood(mood)}
          >
            {mood}
            {mood === defaultMood ? " · 默认" : ""}
          </button>
        ))}
      </div>
      <div className="grid flex-1 gap-4 rounded-[20px] bg-white p-5">
        <div className="text-xs text-[#7A8593]">
          当前心情：
          <span className="ml-1 font-medium text-[#2A3440]">{activeMood || "未选择"}</span>
        </div>
        <div className="grid min-h-[260px] place-items-center overflow-hidden rounded-[18px] bg-[#F2F5F8]">
          {activeMoodIllustrationPath ? (
            <img
              className="max-h-full max-w-full object-contain"
              src={activeMoodIllustrationAbsPath}
              alt={`${activeMood} preview`}
            />
          ) : (
            <div className="px-6 text-center text-sm text-[#74808D]">当前心情还没有绑定差分立绘</div>
          )}
        </div>
        <div className="rounded-[18px] border border-[#E4EAF0] bg-[#F8FBFD] px-4 py-3 text-sm text-[#596776]">
          <div className="truncate">已绑定素材：{activeMoodIllustrationPath || "未设置"}</div>
          <div className="mt-1 truncate">当前选中素材：{selectedAssetPath || "未选择"}</div>
        </div>
        <div className="flex gap-2.5">
          <button
            className={cx("ghost-btn text-sm", ghostButtonClass)}
            type="button"
            onClick={onBindSelectedAsset}
            disabled={!selectedAssetPath || !activeMood}
          >
            绑定当前素材
          </button>
          <button
            className={cx("ghost-btn text-sm", ghostButtonClass)}
            type="button"
            onClick={onClearMoodBinding}
            disabled={!activeMoodIllustrationPath}
          >
            清除绑定
          </button>
        </div>
      </div>
    </div>
  );
}
