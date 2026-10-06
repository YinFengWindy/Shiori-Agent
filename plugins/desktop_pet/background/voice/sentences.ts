/** Removes non-spoken markup and stage directions before synthesis. */
export function spokenText(value: string) {
  const fences = [...value.matchAll(/```/g)];
  if (fences.length % 2) value = value.slice(0, fences.at(-1)!.index);
  value = value.replace(/```[\s\S]*?```/g, "").replace(/!\[[^\]]*\]\([^)]*\)/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/[`*_~#]/g, "");
  let depth = 0; let result = "";
  for (const char of value) {
    if (char === "(" || char === "（") depth += 1;
    else if ((char === ")" || char === "）") && depth) depth -= 1;
    else if (!depth && !/[\p{S}\p{Cf}]/u.test(char)) result += char;
  }
  return result.replace(/\s+/g, " ").trim();
}

/** Incremental sentence buffering is owned by the consuming pet, never the native player. */
export class SpeechSentenceBuffer {
  private buffer = "";
  push(value: string, final = false) {
    this.buffer += value;
    const result: string[] = [];
    let depth = 0; let code = false;
    for (let index = 0; index < this.buffer.length; index += 1) {
      if (this.buffer.startsWith("```", index)) { code = !code; index += 2; continue; }
      if (code) continue;
      const char = this.buffer[index];
      if (char === "(" || char === "（") depth += 1;
      else if ((char === ")" || char === "）") && depth) depth -= 1;
      if (!depth && (/[。！？；!?;\n]/.test(char) || index >= 80)) {
        const sentence = spokenText(this.buffer.slice(0, index + 1));
        if (/[\p{L}\p{N}]/u.test(sentence)) result.push(sentence);
        this.buffer = this.buffer.slice(index + 1); index = -1;
      }
    }
    if (final) { const tail = spokenText(this.buffer); if (/[\p{L}\p{N}]/u.test(tail)) result.push(tail); this.buffer = ""; }
    return result;
  }
}
