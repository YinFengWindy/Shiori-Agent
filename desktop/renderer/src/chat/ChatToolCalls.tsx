import React from "react";
import {
  CaretDown,
  CheckCircle,
  CircleNotch,
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
        <div className="overflow-hidden">
          <div className="mt-1.5 flex flex-col gap-1">
            {calls.map((call) => {
              const callExpanded = expandedCalls.has(call.call_id);
              const details = formatToolArguments(
                Object.keys(call.final_arguments).length > 0
                  ? call.final_arguments
                  : call.arguments,
              );
              return (
                <div key={call.call_id} className="rounded-md border border-[#E4E7EC] bg-[#F8FAFC]">
                  <button
                    type="button"
                    aria-expanded={callExpanded}
                    className="flex w-full min-w-0 items-center gap-2 px-2 py-1.5 text-left text-[12px] text-[#4B5563] transition-colors duration-150 hover:bg-white"
                    onClick={() => toggleCall(call.call_id)}
                  >
                    <ToolStatusIcon status={call.status} />
                    <span className="shrink-0 font-medium text-[#344054]">{call.name}</span>
                    <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-[#8A94A3]">{details}</span>
                    <CaretDown
                      size={12}
                      className={cx("shrink-0 transition-transform duration-200", callExpanded && "rotate-180")}
                      aria-hidden="true"
                    />
                  </button>
                  <div className={cx("chat-tool-call-detail", callExpanded && "chat-tool-call-detail-expanded")}>
                    <div className="overflow-hidden">
                      <div className="border-t border-[#E4E7EC] px-2 py-2">
                        <div className="font-mono text-[11px] leading-5 text-[#667085]">{details}</div>
                        {call.result ? (
                          <pre className="mt-1.5 max-h-36 overflow-auto rounded-md bg-white px-2 py-1.5 text-[11px] leading-5 text-[#596273]">{call.result}</pre>
                        ) : null}
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

function ToolStatusIcon({ status }: { status: ChatToolCall["status"] }) {
  if (status === "running") {
    return <CircleNotch size={14} className="chat-tool-running shrink-0 text-[#7A8492]" aria-label="执行中" />;
  }
  if (status === "success") {
    return <CheckCircle size={14} weight="fill" className="shrink-0 text-[#398A68]" aria-label="执行成功" />;
  }
  return <WarningCircle size={14} weight="fill" className="shrink-0 text-[#B45353]" aria-label="执行失败" />;
}

function formatToolArguments(value: Record<string, unknown>): string {
  const text = JSON.stringify(value);
  if (!text || text === "{}") return "无参数";
  return text.length > 120 ? `${text.slice(0, 117)}...` : text;
}
