import { PrimaryDisplayUnavailableError } from "./types.js";

type DisplayCaptureSource = {
  display_id: string;
};

/** Resolves exactly the primary-display source and refuses an ambiguous fallback. */
export function selectPrimaryDisplaySource<T extends DisplayCaptureSource>(
  primaryDisplayId: string | number,
  sources: readonly T[],
): T {
  const source = sources.find(
    (candidate) => String(candidate.display_id) === String(primaryDisplayId),
  );
  if (!source) throw new PrimaryDisplayUnavailableError("无法解析 Windows 主屏幕捕获源");
  return source;
}
