import { useRef, useState } from "react";
import { flushSync } from "react-dom";
import { compactGhostButtonClass } from "@yinfengwindy/shiori-sdk";

/** Pin the displayed terminal snapshot until the user asks to replace it. */
export function TaskOutput({ output }: { output: string }) {
  const element = useRef<HTMLPreElement>(null);
  const [displayed, setDisplayed] = useState(output);
  const hasNew = output !== displayed;
  const showLatest = () => {
    // Measure only after React commits the replacement window, which may be a different height.
    flushSync(() => setDisplayed(output));
    const node = element.current;
    if (node) node.scrollTop = node.scrollHeight;
  };
  return <section className="min-w-0" aria-label="最近输出">
    <div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-body font-medium">最近输出</h3>
      {hasNew ? <button type="button" className={compactGhostButtonClass} onClick={showLatest}>查看最新输出</button> : null}
    </div>
    <pre ref={element} tabIndex={0} aria-label="任务终端输出" className="herdr-output overflow-auto rounded-md border border-line-soft bg-surface-soft p-4 font-mono text-caption leading-relaxed text-ink-secondary">{displayed || "暂无输出"}</pre>
  </section>;
}
