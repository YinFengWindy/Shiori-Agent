/**
 * Command-line budget for one `node --test` child process.
 *
 * Windows caps a whole CreateProcess command line at 32767 UTF-16 units, and
 * the desktop suite passes every test file as its own argument; with a few
 * hundred files a single spawn fails with `ENAMETOOLONG` long before Linux
 * would notice. The budget leaves headroom for the interpreter path, the
 * fixed runner flags and per-argument quoting.
 */
export const MAX_BATCH_ARGUMENT_CHARS = 24_000;

/**
 * Splits `files` into consecutive batches whose joined argument length stays
 * within `maxChars`, preserving the input order so runs stay deterministic.
 *
 * Each argument is costed as its length plus a separating space and a pair of
 * quotes, which is what Windows command-line quoting adds in the worst
 * common case. A single argument that cannot fit on its own is an error rather
 * than a silently oversized batch.
 */
export function batchByArgumentLength(files, maxChars = MAX_BATCH_ARGUMENT_CHARS) {
  const batches = [];
  let current = [];
  let currentChars = 0;
  for (const file of files) {
    const cost = file.length + 3;
    if (cost > maxChars) {
      throw new Error(`test file path exceeds the per-batch budget (${maxChars}): ${file}`);
    }
    if (current.length && currentChars + cost > maxChars) {
      batches.push(current);
      current = [];
      currentChars = 0;
    }
    current.push(file);
    currentChars += cost;
  }
  if (current.length) batches.push(current);
  return batches;
}
