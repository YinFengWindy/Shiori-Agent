// Conventional Commit types shown to users, in output order; all other types are omitted.
const groups = [
  { title: "新增", types: ["feat"] },
  { title: "修复", types: ["fix"] },
  { title: "改进", types: ["style", "refactor", "perf"] },
];
// Changes outside the desktop app itself (the website) are never listed.
const excludedScopes = new Set(["site"]);
const fallback = "本次更新为内部维护与稳定性改进。";

const bullet = /^[*-]\s+(.+?)(?:\s+by\s+@[\w.-]+(?:\[bot\])?)?(?:\s+in\s+https:\/\/\S+\/pull\/(\d+))?\s*$/;
const conventional = /^(\w+)(?:\(([^)]*)\))?!?:\s*(.+)$/;

function entryOf(line) {
  const item = line.match(bullet);
  if (!item) return undefined;
  const title = item[1].match(conventional);
  // Titles without a Conventional Commit prefix are older English PRs; omit them so
  // untranslated text never reaches the Chinese notes.
  if (!title) return undefined;
  const [, type, scope = "", rawDescription] = title;
  const group = groups.find((candidate) => candidate.types.includes(type.toLowerCase()));
  const scopes = scope.split(",").map((value) => value.trim().toLowerCase()).filter(Boolean);
  if (!group || (scopes.length > 0 && scopes.every((value) => excludedScopes.has(value)))) return undefined;
  // Issue references such as "(#776)" are dropped; the PR number is appended instead.
  const description = rawDescription.replace(/(?:\s*\(#\d+\))+\s*$/, "").trim();
  return { group, text: item[2] ? `${description}（#${item[2]}）` : description };
}

/** Converts GitHub generate-notes Markdown into grouped Chinese user-facing notes. */
export function chineseReleaseNotes(generated) {
  const entries = [];
  let ignored = false;
  for (const line of generated.split(/\r?\n/)) {
    const heading = line.match(/^#{1,6}\s+(.*)$/);
    if (heading) {
      // New Contributors lists people, not changes.
      ignored = /new contributors/i.test(heading[1]);
      continue;
    }
    const entry = ignored ? undefined : entryOf(line.trim());
    if (entry) entries.push(entry);
  }
  const sections = groups
    .map((group) => ({ group, lines: entries.filter((entry) => entry.group === group).map((entry) => `- ${entry.text}`) }))
    .filter((section) => section.lines.length > 0)
    .map((section) => `## ${section.group.title}\n\n${section.lines.join("\n")}`);
  return sections.length > 0 ? sections.join("\n\n") : fallback;
}
