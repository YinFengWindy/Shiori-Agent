import { useState } from "react";
import { ghostButtonClass, textareaClass, type PluginAccountDetailComponentProps } from "@yinfengwindy/shiori-sdk";

/** Preview and copy the credential-free instructions generated for this account. */
export function RoutineConfiguration({ text, host }: {
  text: string;
  host: PluginAccountDetailComponentProps["host"];
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      host.feedback.error("复制失败");
    }
  }

  return <div className="grid gap-2 border-t border-line-soft pt-4">
    <details>
      <summary className="text-body-sm text-ink-secondary">Routine 配置</summary>
      <textarea className={textareaClass} aria-label="Routine 配置内容" rows={10} readOnly value={text} />
    </details>
    <button type="button" className={ghostButtonClass} onClick={() => void copy()}>{copied ? "已复制" : "复制 Routine 配置"}</button>
  </div>;
}
