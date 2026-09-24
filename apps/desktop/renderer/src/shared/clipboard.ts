/**
 * Writes text to the system clipboard. Uses the async Clipboard API when the
 * renderer has it and falls back to a hidden textarea + `execCommand` for
 * contexts where it is unavailable. Rejects when the copy fails.
 */
export async function copyTextToClipboard(text: string): Promise<void> {
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("剪贴板不可用");
}
