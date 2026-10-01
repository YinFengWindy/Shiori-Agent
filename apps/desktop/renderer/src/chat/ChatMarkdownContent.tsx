import React from "react";
import Markdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkCjkFriendly from "remark-cjk-friendly";
import remarkGfm from "remark-gfm";
import type { Components, ExtraProps } from "react-markdown";
import { normalizeExternalLink } from "../../../src/externalLinks";
import { ChatCodeBlock } from "./ChatCodeBlock";
import { getChatCodeLanguage } from "./chatCodeHighlight";

type HastElement = NonNullable<ExtraProps["node"]>;
type HastContent = HastElement["children"][number];

/** Concatenates the text of a hast subtree (the raw source of a code block). */
function hastText(node: HastContent): string {
  if (node.type === "text") return node.value;
  if (node.type === "element") return node.children.map(hastText).join("");
  return "";
}

const tableCellClass = "border-line-soft px-3 py-1.5 text-left align-top";

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
    return (
      <div className="chat-markdown-table my-2 max-w-full overflow-x-auto rounded-md border border-line-soft bg-white/60">
        <table className="w-full border-collapse text-[13px] leading-5">{children}</table>
      </div>
    );
  },
  thead({ children }) { return <thead className="bg-accent-softer">{children}</thead>; },
  tbody({ children }) { return <tbody className="[&>tr:nth-child(even)]:bg-surface-soft">{children}</tbody>; },
  th({ children, style }) { return <th className={`${tableCellClass} whitespace-nowrap border-b font-semibold text-ink`} style={style}>{children}</th>; },
  td({ children, style }) { return <td className={`${tableCellClass} border-t`} style={style}>{children}</td>; },
  pre({ node, children }) {
    // Fenced blocks arrive as <pre><code class="language-x">; render them from
    // the source text so the header, copy button and highlighting see raw code.
    const codeNode = node?.children[0];
    if (codeNode?.type !== "element" || codeNode.tagName !== "code") return <pre>{children}</pre>;
    const className = codeNode.properties.className;
    const language = getChatCodeLanguage(Array.isArray(className) ? className.join(" ") : String(className ?? ""));
    return <ChatCodeBlock code={hastText(codeNode).replace(/\n$/, "")} language={language} />;
  },
  code({ children }) {
    // Only inline code reaches here: fenced blocks are rendered whole by `pre`.
    return <code className="rounded-md bg-surface-soft px-1 py-0.5 font-mono text-[0.9em]">{children}</code>;
  },
  blockquote({ children }) {
    return <blockquote className="my-2 border-l-2 border-line pl-3 text-ink-muted">{children}</blockquote>;
  },
  hr() {
    return <hr className="my-3 border-0 border-t border-line-soft" />;
  },
  h1({ children }) { return <h1 className="my-3 text-lg font-semibold">{children}</h1>; },
  h2({ children }) { return <h2 className="my-2.5 text-base font-semibold">{children}</h2>; },
  h3({ children }) { return <h3 className="my-2 text-sm font-semibold">{children}</h3>; },
  h4({ children }) { return <h4 className="my-2 font-semibold">{children}</h4>; },
  h5({ children }) { return <h5 className="my-2 font-semibold text-ink-muted">{children}</h5>; },
  h6({ children }) { return <h6 className="my-2 font-semibold text-ink-muted">{children}</h6>; },
  p({ children }) { return <p className="my-2 first:mt-0 last:mb-0">{children}</p>; },
  ul({ children }) { return <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>; },
  ol({ children }) { return <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>; },
};

// cjk-friendly lets `**“引号”**` / `**标题：**` close emphasis next to CJK
// punctuation; breaks keeps the model's single newlines as visible line breaks.
const remarkPlugins = [remarkGfm, remarkCjkFriendly, remarkBreaks];

type ChatMarkdownContentProps = {
  content: string;
};

/** Renders assistant Markdown, keeping HTML visible as escaped text and guarding links. */
export const ChatMarkdownContent = React.memo(function ChatMarkdownContent({ content }: ChatMarkdownContentProps) {
  return (
    <div className="message-content message-markdown break-words">
      <Markdown remarkPlugins={remarkPlugins} components={markdownComponents}>
        {content}
      </Markdown>
    </div>
  );
});
