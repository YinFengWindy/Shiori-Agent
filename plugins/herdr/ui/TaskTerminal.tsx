import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowDown } from "@phosphor-icons/react";
import { compactGhostButtonClass, cx, useLatestRef } from "@yinfengwindy/shiori-sdk";

/** Distance from the end that still counts as reading the newest output. */
const bottomSlackPx = 24;

/**
 * The run's terminal window. At the bottom it follows new output; once the
 * user scrolls up it keeps showing the text being read (the service replaces
 * the whole window, so new text would otherwise move under the reader) and
 * offers a way back. The parent keys it by task and run, which resets both.
 */
export function TaskTerminal({ output }: { output: string }) {
  const element = useRef<HTMLPreElement>(null);
  // null while following; otherwise the output the user scrolled up in.
  const [held, setHeld] = useState<string | null>(null);
  const shown = held ?? output;

  useLayoutEffect(() => {
    const node = element.current;
    if (held === null && node) node.scrollTop = node.scrollHeight;
  }, [held, shown]);

  // A resized window changes the viewport, not the content: stay at the end while following.
  const following = useLatestRef(held === null);
  useEffect(() => {
    const node = element.current;
    if (!node) return;
    const observer = new ResizeObserver(() => {
      if (following.current) node.scrollTop = node.scrollHeight;
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [following]);

  const onScroll = () => {
    const node = element.current;
    if (!node) return;
    const atBottom = node.scrollHeight - node.scrollTop - node.clientHeight <= bottomSlackPx;
    if (atBottom && held !== null) setHeld(null);
    if (!atBottom && held === null) setHeld(output);
  };

  return (
    <section className="relative flex min-h-[18rem] flex-1 flex-col" aria-label="终端输出">
      <pre
        ref={element}
        tabIndex={0}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap rounded-md border border-line-soft bg-surface-soft p-4 font-mono text-caption leading-relaxed text-ink-secondary [overflow-wrap:anywhere]"
      >
        {shown || "暂无输出"}
      </pre>
      {held !== null && held !== output ? (
        <button type="button" className={cx(compactGhostButtonClass, "absolute bottom-3 right-5 shadow-soft")} onClick={() => setHeld(null)}>
          <ArrowDown className="h-4 w-4" aria-hidden="true" />
          有新输出
        </button>
      ) : null}
    </section>
  );
}
