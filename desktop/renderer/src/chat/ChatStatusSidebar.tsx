type ChatStatusSidebarProps = {
  currentMood: string;
  moodIllustrationUrl: string;
};

/** Renders the chat status sidebar with the current mood and mapped illustration. */
export function ChatStatusSidebar({
  currentMood,
  moodIllustrationUrl,
}: ChatStatusSidebarProps) {
  return (
    <div className="grid h-full min-h-0 rounded-[20px] bg-[#FBFCFE] p-3 shadow-[0_8px_24px_rgba(15,23,42,0.05)]">
      <div className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-3 rounded-[16px] bg-[#F4F7FB] p-3">
        <div className="grid min-h-0 place-items-center overflow-hidden rounded-[16px] bg-white p-4">
          <img
            className="max-h-full max-w-full object-contain"
            src={moodIllustrationUrl}
            alt={currentMood ? `${currentMood} status illustration` : "status illustration"}
          />
        </div>
        <div className="text-center">
          <div className="text-[11px] uppercase tracking-[0.16em] text-[#7A8593]">当前状态</div>
          <div className="mt-1 text-sm font-semibold text-[#1F2937]">
            {currentMood || "未生成"}
          </div>
        </div>
      </div>
    </div>
  );
}
