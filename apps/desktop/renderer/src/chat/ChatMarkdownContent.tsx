import React from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { normalizeExternalLink } from "../../../src/externalLinks";

const markdownComponents: Components = {
  a({ href, children }) {
    const safeHref = href ? normalizeExternalLink(href) : null;
    if (!safeHref) return <>{children}</>;
    return (
      <a
        href={safeHref}
        rel="noreferrer"
        onClick={(event) => {
          event.preventDefault();
          void window.miraDesktop.openExternal(safeHref);
        }}
      >
        {children}
      </a>
    );
  },
  img({ alt }) {
    return alt ? <span>{alt}</span> : null;
  },
  table({ children }) {
    return <div className="my-2 max-w-full overflow-x-auto"><table>{children}</table></div>;
  },
  pre({ children }) {
    return <pre className="my-2 max-w-full overflow-x-auto rounded-md bg-[#F4F5F7] p-3 font-mono text-[12px] leading-5">{children}</pre>;
  },
  code({ className, children }) {
    const isBlock = Boolean(className);
    return isBlock
      ? <code className={className}>{children}</code>
      : <code className="rounded-md bg-[#F0F1F3] px-1 py-0.5 font-mono text-[0.9em]">{children}</code>;
  },
  blockquote({ children }) {
    return <blockquote className="my-2 border-l-2 border-[#C9CED8] pl-3 text-[#626A78]">{children}</blockquote>;
  },
  hr() {
    return <hr className="my-3 border-0 border-t border-[#D8DDE5]" />;
  },
  h1({ children }) { return <h1 className="my-3 text-lg font-semibold">{children}</h1>; },
  h2({ children }) { return <h2 className="my-2.5 text-base font-semibold">{children}</h2>; },
  h3({ children }) { return <h3 className="my-2 text-sm font-semibold">{children}</h3>; },
  p({ children }) { return <p className="my-2 first:mt-0 last:mb-0">{children}</p>; },
  ul({ children }) { return <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>; },
  ol({ children }) { return <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>; },
};

type ChatMarkdownContentProps = {
  content: string;
};

/** Renders assistant Markdown without allowing raw HTML or unsafe link protocols. */
export const ChatMarkdownContent = React.memo(function ChatMarkdownContent({ content }: ChatMarkdownContentProps) {
  return (
    <div className="message-content message-markdown break-words">
      <Markdown remarkPlugins={[remarkGfm]} skipHtml components={markdownComponents}>
        {content}
      </Markdown>
    </div>
  );
});
