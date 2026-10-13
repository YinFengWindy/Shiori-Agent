import { runInNewContext } from "node:vm";

/**
 * Runs the home page's loader gate script (lib/siteLoaderGate.ts) as a
 * browser would, in a context holding nothing but the globals it reads, and
 * returns the attributes it set on `<html>`.
 */
export function runLoaderGate(script: string, visit: { navigationType: string | undefined; hash: string }) {
  const marked: string[] = [];
  runInNewContext(script, {
    performance: {
      getEntriesByType: (type: string) => (type === "navigation" && visit.navigationType ? [{ type: visit.navigationType }] : []),
    },
    location: { hash: visit.hash },
    document: { documentElement: { setAttribute: (name: string) => marked.push(name) } },
  });
  return marked;
}
