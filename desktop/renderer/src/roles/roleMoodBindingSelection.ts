/** Resolves which mood currently owns the selected illustration path. */
export function getMoodForIllustration(
  illustrationPath: string,
  bindings: Record<string, string>,
): string {
  if (!illustrationPath) {
    return "";
  }
  const matchedEntry = Object.entries(bindings).find(([, path]) => path === illustrationPath);
  return matchedEntry?.[0] ?? "";
}

/** Applies an illustration-to-mood mapping while keeping illustration ownership unique. */
export function applyMoodToIllustration(
  previousBindings: Record<string, string>,
  illustrationPath: string,
  nextMood: string,
): Record<string, string> {
  const normalizedPath = illustrationPath.trim();
  if (!normalizedPath) {
    return previousBindings;
  }
  const normalizedMood = nextMood.trim();
  const nextBindings = Object.fromEntries(
    Object.entries(previousBindings).filter(([mood, path]) => mood !== normalizedMood && path !== normalizedPath),
  );
  if (!normalizedMood) {
    return nextBindings;
  }
  nextBindings[normalizedMood] = normalizedPath;
  return nextBindings;
}
