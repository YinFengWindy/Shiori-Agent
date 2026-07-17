import React from "react";
import { ChatStatusSidebar } from "./ChatStatusSidebar";
import { RoleTasksPanel } from "./RoleTasksPanel";
import { toFileUrl } from "../shared/format";
import type { RoleTask, ScheduleTaskFormData } from "../shared/types";

export type ChatSidebarMode = "status" | "images" | "tasks";

type ChatRightSidebarProps = {
  canGoToNextImage: boolean;
  canGoToPreviousImage: boolean;
  currentMood: string;
  imagePath: string;
  lonelinessValue: number;
  mode: ChatSidebarMode;
  moodIllustrationUrl: string;
  relationshipTags: string[];
  renderHeavyVisuals: boolean;
  roleSelfView: string;
  tasks: RoleTask[];
  taskError: string;
  taskOperation: { kind: "create" | "update" | "cancel"; taskId: string } | null;
  onClearTaskError: () => void;
  onCreateTask: (data: ScheduleTaskFormData) => Promise<RoleTask>;
  onUpdateTask: (taskId: string, data: ScheduleTaskFormData) => Promise<RoleTask>;
  onCancelTask: (taskId: string) => Promise<void>;
  onGoToNextImage: () => void;
  onGoToPreviousImage: () => void;
  onOpenImageLightbox: () => void;
};

/** Renders the active status, task, or image panel in the chat right sidebar. */
export const ChatRightSidebar = React.memo(function ChatRightSidebar({
  canGoToNextImage,
  canGoToPreviousImage,
  currentMood,
  imagePath,
  lonelinessValue,
  mode,
  moodIllustrationUrl,
  relationshipTags,
  renderHeavyVisuals,
  roleSelfView,
  tasks,
  taskError,
  taskOperation,
  onClearTaskError,
  onCreateTask,
  onUpdateTask,
  onCancelTask,
  onGoToNextImage,
  onGoToPreviousImage,
  onOpenImageLightbox,
}: ChatRightSidebarProps) {
  const navButtonClass =
    "pointer-events-auto grid h-9 w-9 place-items-center rounded-full border border-transparent bg-transparent text-[#4B5563] transition hover:border-black hover:bg-white/92 hover:text-[#1F2937] focus:outline-none disabled:cursor-default disabled:opacity-40";
  if (mode === "status") {
    return (
      <ChatStatusSidebar
        currentMood={currentMood}
        moodIllustrationUrl={moodIllustrationUrl}
        roleSelfView={roleSelfView}
        relationshipTags={relationshipTags}
        lonelinessValue={lonelinessValue}
        visualsActive={renderHeavyVisuals}
      />
    );
  }
  if (mode === "tasks") {
    return (
      <RoleTasksPanel
        tasks={tasks}
        operation={taskOperation}
        error={taskError}
        onClearError={onClearTaskError}
        onCreate={onCreateTask}
        onUpdate={onUpdateTask}
        onCancel={onCancelTask}
      />
    );
  }
  return (
    <div className="grid h-full min-h-0 rounded-[20px] bg-[#F1F5F9] p-3 shadow-[0_8px_24px_rgba(15,23,42,0.05)]">
      <div className="relative grid h-full min-h-0 place-items-center overflow-hidden rounded-[16px] bg-[#F1F5F9]">
        <div className="pointer-events-none absolute inset-y-0 left-0 z-[2] flex items-center pl-3">
          <button className={navButtonClass} type="button" aria-label="查看上一张聊天图片" onClick={onGoToPreviousImage} disabled={!canGoToPreviousImage}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m15 18-6-6 6-6" />
            </svg>
          </button>
        </div>
        {imagePath && renderHeavyVisuals ? (
          <button className="grid h-full w-full place-items-center border-0 bg-transparent p-0" type="button" aria-label="放大查看当前聊天图片" onClick={onOpenImageLightbox}>
            <img className="max-h-full max-w-full object-contain" src={toFileUrl(imagePath)} alt="selected message image" decoding="async" />
          </button>
        ) : (
          <div className="grid gap-2 px-6 text-center">
            <div className="mx-auto h-10 w-10 rounded-[14px] border border-[#D6DCE5] bg-white/70" />
            <div className="text-[12px] text-[#6B7280]">当前聊天里出现的图片会显示在这里</div>
          </div>
        )}
        <div className="pointer-events-none absolute inset-y-0 right-0 z-[2] flex items-center pr-3">
          <button className={navButtonClass} type="button" aria-label="查看下一张聊天图片" onClick={onGoToNextImage} disabled={!canGoToNextImage}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m9 18 6-6-6-6" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
});
