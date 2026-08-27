import React from "react";
import {
  CaretDown,
  CircleNotch,
  FileText,
  MagnifyingGlass,
  PencilSimple,
  TerminalWindow,
  WarningCircle,
  Wrench,
} from "@phosphor-icons/react";
import type { ChatToolCall, ChatToolCallGroup } from "../shared/types";
import { cx } from "../shared/styles";

type ChatToolCallsProps = {
  groups: ChatToolCallGroup[];
  streaming: boolean;
};

/** Renders compact expandable tool call records inside one assistant reply. */
export const ChatToolCalls = React.memo(function ChatToolCalls({
  groups,
  streaming,
}: ChatToolCallsProps) {
  const calls = groups.flatMap((group) => group.calls);
  const [expanded, setExpanded] = React.useState(streaming);
  const [expandedCalls, setExpandedCalls] = React.useState<Set<string>>(() => new Set());
  const previousStreaming = React.useRef(streaming);

  React.useEffect(() => {
    if (previousStreaming.current && !streaming) {
      setExpanded(false);
      setExpandedCalls(new Set());
    }
    previousStreaming.current = streaming;
  }, [streaming]);

  if (calls.length === 0) return null;
  const runningCount = calls.filter((call) => call.status === "running").length;

  function toggleCall(callId: string) {
    setExpandedCalls((current) => {
      const next = new Set(current);
      if (next.has(callId)) next.delete(callId);
      else next.add(callId);
      return next;
    });
  }

  return (
    <div className="chat-tool-calls mb-2 max-w-full">
      <button
        type="button"
        aria-expanded={expanded}
        className="-mx-1.5 flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[12.5px] text-[#626A78] transition-colors duration-150 hover:bg-black/[0.04]"
        onClick={() => setExpanded((current) => !current)}
      >
        <CaretDown
          size={13}
          className={cx("transition-transform duration-200", expanded && "rotate-180")}
          aria-hidden="true"
        />
        <Wrench size={13} aria-hidden="true" />
        <span>{`${calls.length} 次工具调用`}</span>
        {runningCount > 0 ? <span className="text-[#8B95A7]">{`${runningCount} 个执行中`}</span> : null}
      </button>
      <div className={cx("chat-tool-call-content", expanded && "chat-tool-call-content-expanded")}>
        <div className="min-h-0 overflow-hidden">
          <div className="mt-1.5 flex flex-col gap-1">
            {calls.map((call) => {
              const callExpanded = expandedCalls.has(call.call_id);
              const details = formatToolArguments(
                Object.keys(call.final_arguments).length > 0
                  ? call.final_arguments
                  : call.arguments,
              );
              return (
                <div key={call.call_id}>
                  <button
                    type="button"
                    aria-expanded={callExpanded}
                    className="group/tool-row -mx-[3px] flex h-7 w-[calc(100%+6px)] min-w-0 items-center gap-2 rounded-md px-[3px] text-left transition-colors duration-100 hover:bg-black/[0.04]"
                    onClick={() => toggleCall(call.call_id)}
                  >
                    <span className="relative flex size-4 shrink-0 items-center justify-center text-[#8B95A7]">
                      <ToolStatusIcon name={call.name} status={call.status} />
                      {call.status !== "running" ? (
                        <CaretDown
                          size={12}
                          className={cx(
                            "chat-tool-expand-icon absolute inset-0 m-auto opacity-0 transition-[opacity,transform] duration-150 group-hover/tool-row:opacity-100",
                            callExpanded ? "rotate-180" : "-rotate-90",
                          )}
                          aria-hidden="true"
                        />
                      ) : null}
                    </span>
                    <span className="shrink-0 text-[12.5px] font-medium text-[#343B47]">{call.name}</span>
                    <span className="chat-tool-argument-chip inline-flex h-[22px] min-w-0 flex-1 items-center truncate rounded-md bg-black/[0.045] px-1.5 font-mono text-[11.5px] text-[#606875] shadow-[inset_0_0_0_1px_rgba(17,24,39,0.04)] transition-colors duration-100 group-hover/tool-row:bg-black/[0.065]">
                      {details}
                    </span>
                  </button>
                  <div className={cx("chat-tool-call-detail", callExpanded && "chat-tool-call-detail-expanded")}>
                    <div className="min-h-0 overflow-hidden">
                      <div className="mb-1 ml-2 mt-0.5 border-l border-[#E1E5EA] py-0.5 pl-3.5">
                        {call.result ? (
                          <pre className={cx(
                            "max-h-36 overflow-auto whitespace-pre-wrap break-words font-mono text-[11.5px] leading-[1.6] text-[#667085]",
                            call.status !== "success" && call.status !== "running" && "text-[#A55454]",
                          )}>{call.result}</pre>
                        ) : <span className="text-[11.5px] leading-[1.6] text-[#98A0AD]">暂无结果</span>}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
});

function ToolStatusIcon({ name, status }: { name: string; status: ChatToolCall["status"] }) {
  if (status === "running") {
    return <CircleNotch size={13} className="chat-tool-status-icon chat-tool-running absolute inset-0 m-auto" aria-label="执行中" />;
  }
  if (status !== "success") {
    return <WarningCircle size={13} weight="fill" className="chat-tool-status-icon absolute inset-0 m-auto text-[#B25D5D] transition-opacity duration-100 group-hover/tool-row:opacity-0" aria-label="执行失败" />;
  }
  const normalized = name.toLowerCase();
  const Icon = normalized.includes("search")
    ? MagnifyingGlass
    : normalized.includes("read") || normalized.includes("file")
      ? FileText
      : normalized.includes("write") || normalized.includes("edit")
        ? PencilSimple
        : normalized.includes("shell") || normalized.includes("command")
          ? TerminalWindow
          : Wrench;
  return <Icon size={13} className="chat-tool-status-icon absolute inset-0 m-auto transition-opacity duration-100 group-hover/tool-row:opacity-0" aria-label="执行成功" />;
}

function formatToolArguments(value: Record<string, unknown>): string {
  const text = JSON.stringify(value);
  if (!text || text === "{}") return "无参数";
  return text.length > 120 ? `${text.slice(0, 117)}...` : text;
}
