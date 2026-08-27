import { useEffect, useState } from "react";
import { inputClass } from "../shared/styles";

type RoleMoodBindingsPanelProps = {
  selectedAssetPath: string;
  selectedAssetAbsPath: string;
  selectedMood: string;
  onSaveMoodBinding: (nextMood: string) => void;
  onClearSelectedAsset: () => void;
};

/** Renders the role asset-side mood binding panel. */
export function RoleMoodBindingsPanel({
  selectedAssetPath,
  selectedAssetAbsPath,
  selectedMood,
  onSaveMoodBinding,
  onClearSelectedAsset,
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
      <div className="grid min-h-[360px] flex-1 gap-4 rounded-[20px] bg-white p-5">
        <div className="relative grid min-h-[260px] place-items-center overflow-hidden rounded-[18px] bg-[#F2F5F8]">
          {selectedAssetPath ? (
            <>
              <button
                className="absolute right-3 top-3 grid h-8 w-8 place-items-center rounded-full border border-black/10 bg-white/92 text-[#5B6472] transition hover:border-[#9AA3B2] hover:bg-white hover:text-[#272536] focus:outline-none"
                type="button"
                onClick={onClearSelectedAsset}
                aria-label="取消选中差分图"
              >
                ×
              </button>
              <img
                className="max-h-full max-w-full object-contain"
                src={selectedAssetAbsPath}
                alt={`${selectedMood || "差分"} preview`}
              />
            </>
          ) : (
            <div className="px-6 text-center text-sm text-[#74808D]">请先在左侧选中一张差分立绘</div>
          )}
        </div>
        <label className="grid w-[240px] gap-1.5 text-xs text-[#374151]">
          <span>对应差分</span>
          <input
            className={`${inputClass} h-10 px-3 py-2 border-[#D8DFE7] bg-white text-[#111827] placeholder:text-[#9CA3AF]`}
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
