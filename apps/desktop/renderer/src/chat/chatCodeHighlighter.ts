import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import c from "highlight.js/lib/languages/c";
import cpp from "highlight.js/lib/languages/cpp";
import csharp from "highlight.js/lib/languages/csharp";
import css from "highlight.js/lib/languages/css";
import diff from "highlight.js/lib/languages/diff";
import go from "highlight.js/lib/languages/go";
import ini from "highlight.js/lib/languages/ini";
import java from "highlight.js/lib/languages/java";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import powershell from "highlight.js/lib/languages/powershell";
import python from "highlight.js/lib/languages/python";
import rust from "highlight.js/lib/languages/rust";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";

// Loaded lazily by `chatCodeHighlight.ts` (its own chunk): the core plus the
// languages a chat reply most often contains. Anything else renders unhighlighted.
const languages = {
  bash, c, cpp, csharp, css, diff, go, ini, java, javascript, json, markdown,
  powershell, python, rust, sql, typescript, xml, yaml,
};
for (const [name, language] of Object.entries(languages)) {
  hljs.registerLanguage(name, language);
}

/**
 * Highlights one code block. Returns HTML whose text is escaped by
 * highlight.js (only its own `<span class="hljs-*">` markup is added), or
 * null for an unknown or missing language.
 */
export function highlightChatCode(code: string, language: string): string | null {
  const name = language.trim().toLowerCase();
  if (!name || !hljs.getLanguage(name)) return null;
  return hljs.highlight(code, { language: name, ignoreIllegals: true }).value;
}
