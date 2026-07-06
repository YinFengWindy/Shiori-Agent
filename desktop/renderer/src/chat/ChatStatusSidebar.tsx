import { cx } from "../shared/styles";

type ChatStatusSidebarProps = {
  currentMood: string;
  moodIllustrationUrl: string;
  hasMoodMapping: boolean;
};

/** Renders the chat status sidebar with the current mood and mapped illustration. */
export function ChatStatusSidebar({
  currentMood,
  moodIllustrationUrl,
  hasMoodMapping,
}: ChatStatusSidebarProps) {
  return (
    <div className="grid h-full min-h-0 rounded-[20px] bg-[#FBFCFE] p-3 shadow-[0_8px_24px_rgba(15,23,42,0.05)]">
      <div className="grid h-full min-h-0 gap-3 rounded-[16px] bg-[#F4F7FB] p-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.16em] text-[#7A8593]">当前状态</div>
            <div className="mt-1 text-sm font-semibold text-[#1F2937]">
              {currentMood || "未生成"}
            </div>
          </div>
          <span
            className={cx(
              "inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium",
              hasMoodMapping
                ? "bg-[rgba(33,120,90,0.08)] text-[#21785A]"
                : "bg-[rgba(122,133,147,0.08)] text-[#7A8593]",
            )}
          >
            {hasMoodMapping ? "已绑定差分" : "使用回退立绘"}
          </span>
        </div>
        <div className="relative grid min-h-0 flex-1 place-items-center overflow-hidden rounded-[16px] bg-white">
          {moodIllustrationUrl ? (
            <img
              className="max-h-full max-w-full object-contain"
              src={moodIllustrationUrl}
              alt={currentMood ? `${currentMood} status illustration` : "status illustration"}
            />
          ) : (
            <div className="grid gap-2 px-6 text-center">
              <div className="mx-auto h-10 w-10 rounded-[14px] border border-[#D6DCE5] bg-white/70" />
              <div className="text-[12px] text-[#6B7280]">当前角色的状态立绘会显示在这里</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
