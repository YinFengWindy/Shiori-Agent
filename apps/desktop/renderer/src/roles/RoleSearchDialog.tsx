import { useDeferredValue, useEffect, useMemo, useRef } from "react";
import { formatTimestamp, toFileUrl } from "../shared/format";
import { emptyStateLines } from "../shared/mascot/mascotLines";
import { MascotEmptyState } from "../shared/mascot/MascotSpeech";
import { useMascotEnabled } from "../shared/mascot/useMascotEnabled";
import { cx } from "../shared/styles";
import type { RoleSearchResult } from "../shared/types";

type RoleSearchDialogProps = {
  open: boolean;
  query: string;
  searching: boolean;
  results: RoleSearchResult[];
  onClose: () => void;
  onSelectResult: (result: RoleSearchResult) => void;
  onUpdateQuery: (value: string) => void;
};

/** Renders the Codex-like role and message search dialog for the desktop sidebar. */
export function RoleSearchDialog({
  open,
  query,
  searching,
  results,
  onClose,
  onSelectResult,
  onUpdateQuery,
}: RoleSearchDialogProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const deferredQuery = useDeferredValue(query);
  const mascotEnabled = useMascotEnabled();
  const noResults = Boolean(deferredQuery.trim()) && !searching;
  const emptyMessage = useMemo(() => {
    if (!deferredQuery.trim()) return "搜索角色名或消息内容";
    if (searching) return "正在整理搜索结果...";
    return "没有找到匹配结果";
  }, [deferredQuery, searching]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const timer = window.setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 10);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.clearTimeout(timer);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;

    function handleEscape(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="role-search-dialog fixed inset-0 z-30 flex items-start justify-center px-4 pb-4 pt-14">
      <button
        className="role-search-backdrop absolute inset-0 border-0 bg-[rgba(15,23,42,0.34)] p-0 backdrop-blur-[6px]"
        type="button"
        aria-label="关闭搜索"
        onClick={onClose}
      />
      <section
        className="role-search-panel relative z-[1] grid max-h-[min(76vh,780px)] w-full max-w-[760px] grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-xl bg-[rgba(255,255,255,0.97)] shadow-pop"
        role="dialog"
        aria-modal="true"
        aria-label="搜索"
      >
        <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)]">
          <div className="px-4 pt-4">
            <input
              ref={inputRef}
              data-testid="role-search-input"
              className={cx(
                "h-12 w-full rounded-md border border-transparent bg-surface-soft px-4 py-0 text-[15px] text-ink outline-none transition-none placeholder:text-ink-faint",
                "hover:border-transparent focus:border-transparent focus:outline-none focus-visible:border-transparent focus-visible:outline-none",
              )}
              value={query}
              onChange={(event) => onUpdateQuery(event.target.value)}
              placeholder="搜索角色名或消息内容"
            />
          </div>
          <div className="role-search-results scrollbar-stable min-h-0 overflow-y-auto px-2.5 pb-2.5 pt-3">
            {results.length ? (
              <div className="grid gap-1.5">
                {results.map((result) => (
                  <button
                    key={`${result.roleId}:${result.matchedField}:${result.matchedMessageId ?? result.roleName}`}
                    data-testid={`role-search-result-${result.roleId}-${result.matchedMessageIndex ?? "role"}`}
                    className="grid w-full grid-cols-[44px_minmax(0,1fr)] items-start gap-3 rounded-lg border-0 bg-transparent px-2.5 py-2.5 text-left transition hover:bg-surface-hover focus-visible:bg-surface-hover"
                    type="button"
                    onClick={() => onSelectResult(result)}
                  >
                    {result.roleAvatarAbs ? (
                      <img
                        className="h-11 w-11 rounded-full border border-[rgba(76,48,24,0.12)] object-cover"
                        src={toFileUrl(result.roleAvatarAbs)}
                        alt={`${result.roleName} avatar`}
                      />
                    ) : (
                      <span className="grid h-11 w-11 place-items-center rounded-full border border-line-soft bg-surface-soft text-sm font-bold text-accent-text">
                        {result.roleName.slice(0, 1).toUpperCase()}
                      </span>
                    )}
                    <span className="grid min-w-0 gap-1">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="min-w-0 truncate text-[14px] font-semibold text-ink">{result.roleName}</span>
                        <span className="rounded-full bg-surface-soft px-2 py-0.5 text-[11px] text-ink-muted">
                          {result.matchedField === "message" ? "消息" : "角色"}
                        </span>
                      </span>
                      <span className="max-h-10 overflow-hidden whitespace-pre-wrap break-words text-[13px] leading-5 text-ink-secondary">
                        {result.matchedMessagePreview}
                      </span>
                      {result.matchedField === "message" && result.matchedMessageTimestamp ? (
                        <span className="text-[11px] text-ink-faint">
                          {formatTimestamp(result.matchedMessageTimestamp)}
                        </span>
                      ) : null}
                    </span>
                  </button>
                ))}
              </div>
            ) : noResults && mascotEnabled ? (
              // 吟风 says 「没找到」 (an owner-approved line, #362 stage 10).
              <div className="grid min-h-[200px] place-items-center px-4 pt-2">
                <MascotEmptyState line={emptyStateLines.noSearchResults} layout="side" size="compact" testId="role-search-empty" />
              </div>
            ) : (
              <div className="grid min-h-[200px] place-items-center px-4 text-center text-[13px] text-ink-faint" data-testid="role-search-empty">
                {emptyMessage}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
