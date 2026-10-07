import { useEffect, useId, useRef, useState } from "react";
import { errorMessage, settingsInputClass, SettingsField, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";

/** Props of `VoiceHotkeyField`: the saved hotkey and where a validated one goes. */
export type VoiceHotkeyFieldProps = {
  client: PluginRpcClient;
  /** The hotkey in the saved preferences draft. */
  value: string;
  /** Receives a hotkey the native layer accepted; never an unvalidated one. */
  onCommit: (hotkey: string) => void;
};

/**
 * The 快捷键 row. Typed text stays local; on blur or Enter it is validated by
 * the background (`voice.preferences.validate`) and only an accepted hotkey
 * is committed. A rejected one stays visible with its error, and the saved
 * hotkey is kept. Escape returns to the saved hotkey.
 */
export function VoiceHotkeyField({ client, value, onCommit }: VoiceHotkeyFieldProps) {
  const [text, setText] = useState(value);
  const [base, setBase] = useState(value);
  const [error, setError] = useState("");
  const attempt = useRef(0);
  const errorId = useId();

  // A new saved hotkey (a commit, a reload) replaces the typed text.
  if (base !== value) {
    setBase(value);
    setText(value);
    setError("");
  }
  // A validation started against another client or saved hotkey, or before unmounting, must not commit.
  useEffect(() => () => { attempt.current += 1; }, [client, value]);

  const submit = async () => {
    if (text === value) {
      setError("");
      return;
    }
    const current = ++attempt.current;
    try {
      await client.background.call("voice.preferences.validate", { hotkey: text });
    } catch (cause) {
      if (attempt.current === current) setError(errorMessage(cause));
      return;
    }
    if (attempt.current !== current) return;
    setError("");
    onCommit(text);
  };

  const revert = () => {
    attempt.current += 1;
    setText(value);
    setError("");
  };

  return (
    <SettingsField label="快捷键">
      <input
        className={settingsInputClass}
        aria-label="快捷键"
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => void submit()}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void submit();
          } else if (event.key === "Escape") {
            revert();
          }
        }}
      />
      {error ? <p id={errorId} className="mt-1.5 text-caption text-danger-text">{error}</p> : null}
    </SettingsField>
  );
}
