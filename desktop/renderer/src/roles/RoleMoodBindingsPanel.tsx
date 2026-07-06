import { useEffect, useState } from "react";
import { cx, inputClass } from "../shared/styles";

type RoleMoodBindingsPanelProps = {
  moodCatalog: string[];
  defaultMood: string;
  selectedAssetPath: string;
  selectedAssetAbsPath: string;
  selectedMood: string;
  onSaveMoodBinding: (nextMood: string) => void;
};

/** Renders the role asset-side mood binding panel. */
export function RoleMoodBindingsPanel({
  moodCatalog,
  defaultMood,
  selectedAssetPath,
  selectedAssetAbsPath,
  selectedMood,
  onSaveMoodBinding,
}: RoleMoodBindingsPanelProps) {
  const [draftMood, setDraftMood] = useState(selectedMood);

  useEffect(() => {
    setDraftMood(selectedMood);
  }, [selectedMood]);

  function handleMoodBlur(): void {
    const normalizedDraft = draftMood.trim();
    if (normalizedDraft === selectedMood.trim()) {
      return;
    }
    onSaveMoodBinding(normalizedDraft);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-4 text-xs text-[#7A8593]">先在左侧选中一张差分图，再为这张图填写对应心情；输入框失焦后会自动保存。</div>
      <div className="mb-4 flex flex-wrap gap-2">
        {moodCatalog.map((mood) => (
          <button
            key={mood}
            className={cx(
              "rounded-full px-4 py-2 text-sm transition",
              selectedMood === mood
                ? "bg-[#272536] text-white shadow-[0_6px_16px_rgba(39,37,54,0.18)]"
                : "border border-[#D8DFE7] bg-white text-[#5B6472] hover:text-[#272536]",
            )}
            type="button"
            onClick={() => {
              setDraftMood(mood);
              onSaveMoodBinding(mood);
            }}
          >
            {mood}
            {mood === defaultMood ? " · 默认" : ""}
          </button>
        ))}
      </div>
      <div className="grid min-h-[360px] flex-1 gap-4 rounded-[20px] bg-white p-5">
        <div className="grid min-h-[260px] place-items-center overflow-hidden rounded-[18px] bg-[#F2F5F8]">
          {selectedAssetPath ? (
            <img
              className="max-h-full max-w-full object-contain"
              src={selectedAssetAbsPath}
              alt={`${selectedMood || "差分"} preview`}
            />
          ) : (
            <div className="px-6 text-center text-sm text-[#74808D]">请先在左侧选中一张差分立绘</div>
          )}
        </div>
        <label className="grid gap-1.5 text-xs text-[#374151]">
          <span>对应心情</span>
          <input
            className={cx(inputClass, "border-[#D8DFE7] bg-white text-[#111827] placeholder:text-[#9CA3AF]")}
            value={draftMood}
            onChange={(event) => setDraftMood(event.target.value.trimStart())}
            onBlur={handleMoodBlur}
            placeholder="例如：平静"
            disabled={!selectedAssetPath}
          />
        </label>
      </div>
    </div>
  );
}
