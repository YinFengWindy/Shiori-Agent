import { useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { PaperPlaneRight } from "@phosphor-icons/react";
import { AutosizeTextarea, compactGhostButtonClass, cx, errorMessage, iconButtonClass, inputClass, type PluginHostServices } from "@yinfengwindy/shiori-sdk";

/** Past this height the input scrolls instead of growing. */
const composerMaxHeight = "12rem";

/** One way to send the draft; `run` rejects to keep the draft and show why. */
export type ComposerAction = {
  /** The button's label (the primary one is an icon button and uses it as its name). */
  label: string;
  /** Heading of the error shown when `run` fails. */
  errorTitle: string;
  /** This way of sending is unavailable; the input stays usable while another one is. */
  disabled: boolean;
  run: (text: string) => Promise<void>;
};

/**
 * The bottom input of the Herdr page. Enter and the icon button send with
 * `primary`; each `secondary` action is a labeled button on the same draft.
 * A successful send clears the draft, a failure keeps it and shows the
 * error; nothing is sent twice while a send is in flight. The parent keys it
 * by its target, so a draft never carries over to another one.
 */
export function Composer({ label, primary, secondary = [], trailing, host }: {
  /** Accessible name and placeholder of the input. */
  label: string;
  primary: ComposerAction;
  secondary?: ComposerAction[];
  /** Controls after the send buttons that do not use the draft. */
  trailing?: ReactNode;
  host: PluginHostServices;
}) {
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<{ title: string; message: string } | null>(null);
  // Guards a second Enter before the pending state renders.
  const inFlight = useRef(false);
  const disabled = primary.disabled && secondary.every((action) => action.disabled);

  const send = async (action: ComposerAction) => {
    if (action.disabled || inFlight.current || !draft.trim()) return;
    inFlight.current = true;
    setPending(true);
    setFailure(null);
    try {
      await action.run(draft);
      setDraft("");
    } catch (reason) {
      setFailure({ title: action.errorTitle, message: errorMessage(reason) });
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(primary);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(primary);
    }
  };
  const sendDisabled = (action: ComposerAction) => action.disabled || pending || !draft.trim();

  return (
    <form className="grid gap-2 border-t border-line-soft px-6 py-4" onSubmit={submit}>
      {failure ? <host.ui.InlineError message={failure.message} title={failure.title} layout="row" /> : null}
      <div className="flex items-end gap-2">
        <AutosizeTextarea
          aria-label={label}
          placeholder={label}
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
        {secondary.map((action) => (
          <button key={action.label} type="button" className={compactGhostButtonClass} disabled={sendDisabled(action)} onClick={() => { void send(action); }}>
            {action.label}
          </button>
        ))}
        <button type="submit" className={iconButtonClass} aria-label={primary.label} disabled={sendDisabled(primary)}>
          <PaperPlaneRight className="h-4 w-4" aria-hidden="true" />
        </button>
        {trailing}
      </div>
    </form>
  );
}
