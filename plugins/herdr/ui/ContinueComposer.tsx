import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { PaperPlaneRight } from "@phosphor-icons/react";
import { AutosizeTextarea, cx, errorMessage, iconButtonClass, inputClass, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { TaskDetail, TaskDetailResponse } from "./types";

/** Past this height the input scrolls instead of growing. */
const composerMaxHeight = "12rem";

/**
 * The always-present 追加要求 input: sending starts the next run of the same
 * agent in the same worktree. Disabled while the service says the task cannot
 * continue or the bridge is down; the parent keys it by task, so a draft
 * never carries over to another task.
 */
export function ContinueComposer({ task, connected, client, host, onApplied }: {
  task: TaskDetail;
  connected: boolean;
  client: PluginRpcClient;
  host: PluginHostServices;
  onApplied: (response: TaskDetailResponse) => void;
}) {
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  // Guards a second Enter before the pending state renders.
  const inFlight = useRef(false);
  const disabled = !connected || !task.can_continue;

  const send = async () => {
    if (disabled || inFlight.current || !draft.trim()) return;
    inFlight.current = true;
    setPending(true);
    setError("");
    try {
      onApplied(await client.call<TaskDetailResponse>("tasks.continue", { task_id: task.id, requirement: draft }));
      setDraft("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  };

  return (
    <form className="grid gap-2 border-t border-line-soft px-6 py-4" onSubmit={submit}>
      {error ? <host.ui.InlineError message={error} title="追加要求未提交" layout="row" /> : null}
      <div className="flex items-end gap-2">
        <AutosizeTextarea
          aria-label="追加要求"
          placeholder="追加要求"
          rows={1}
          value={draft}
          disabled={disabled || pending}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          className={cx(inputClass, "overflow-y-auto")}
          style={{ maxHeight: composerMaxHeight }}
          containerClassName="flex-1"
          containerStyle={{ maxHeight: composerMaxHeight }}
          mirrorClassName="border border-transparent px-3.5 py-2.5 text-body"
        />
        <button type="submit" className={iconButtonClass} aria-label="发送追加要求" disabled={disabled || pending || !draft.trim()}>
          <PaperPlaneRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}
