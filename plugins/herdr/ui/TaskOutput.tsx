import { useRef, useState } from "react";
import { compactGhostButtonClass } from "@yinfengwindy/shiori-sdk";

/** Keep the user's reading position; following the newest output is explicit. */
export function TaskOutput({ output }: { output: string }) {
  const element = useRef<HTMLPreElement>(null);
  const [acknowledged, setAcknowledged] = useState(output);
  const hasNew = output !== acknowledged;
  return <section className="min-w-0" aria-label="最近输出">
    <div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-body font-medium">最近输出</h3>
      {hasNew ? <button type="button" className={compactGhostButtonClass} onClick={() => { const node = element.current; if (node) node.scrollTop = node.scrollHeight; setAcknowledged(output); }}>查看最新输出</button> : null}
    </div>
    <pre ref={element} tabIndex={0} aria-label="任务终端输出" className="herdr-output overflow-auto rounded-md border border-line-soft bg-surface-soft p-4 font-mono text-caption leading-relaxed text-ink-secondary">{output || "暂无输出"}</pre>
  </section>;
}
