/**
 * Node test reporter that emits one JSON line of pass/fail counts.
 *
 * `test-unit.mjs` may run the suite as several `node --test` batches, each
 * printing its own spec summary; this reporter runs next to `spec` and writes
 * machine-readable counts to a per-batch file so the runner can print a single
 * aggregate line. Suites are excluded so the numbers match spec's `tests`
 * count; a file that fails to load surfaces as its own failing test event.
 */
export default async function* summaryReporter(source) {
  const counts = { tests: 0, passed: 0, failed: 0, skipped: 0, todo: 0 };
  for await (const event of source) {
    if (event.type !== "test:pass" && event.type !== "test:fail") continue;
    if (event.data.details?.type === "suite") continue;
    counts.tests += 1;
    // Node never fails a run on todo/skip tests, so they are classified before
    // pass/fail to keep `failed` equal to what decides the exit code.
    if (event.data.todo !== undefined) counts.todo += 1;
    else if (event.data.skip !== undefined) counts.skipped += 1;
    else if (event.type === "test:fail") counts.failed += 1;
    else counts.passed += 1;
  }
  yield `${JSON.stringify(counts)}\n`;
}
