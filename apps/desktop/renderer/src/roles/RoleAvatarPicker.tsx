import { useRef, useState } from "react";
import { Camera } from "@phosphor-icons/react";

/** Selects and previews an optional avatar before a role is persisted. */
export function RoleAvatarPicker({ source, disabled, onChange }: {
  source: string;
  disabled: boolean;
  onChange: (source: string) => void;
}) {
  const [error, setError] = useState("");
  const [picking, setPicking] = useState(false);
  const pending = useRef(false);
  async function pick() {
    if (pending.current || disabled) return;
    pending.current = true;
    setPicking(true);
    setError("");
    try {
      const [path] = await window.miraDesktop.pickImages({ multiple: false });
      if (path) onChange(path);
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      pending.current = false;
      setPicking(false);
    }
  }
  return (
    <div className="grid justify-items-center gap-2">
      <button type="button" aria-label={source ? "更换头像" : "上传头像"} title={source ? "更换头像" : "上传头像"}
        disabled={disabled || picking} onClick={() => void pick()}
        className="group grid h-24 w-24 shrink-0 place-items-center overflow-hidden rounded-full border-4 border-white/90 bg-gradient-accent-soft text-ink-muted shadow-panel transition-colors hover:text-ink disabled:opacity-50">
        {source
          ? <img src={window.miraDesktop.localAssetUrl(source)} alt="角色头像预览" className="h-full w-full object-cover transition-transform duration-panel ease-out-soft motion-safe:group-hover:scale-105" />
          : <Camera className="h-7 w-7" aria-hidden="true" />}
      </button>
      {source
        ? <button type="button" aria-label="移除头像" disabled={disabled || picking} onClick={() => onChange("")}
          className="rounded-md px-1.5 text-caption text-ink-muted transition-colors hover:text-danger-text disabled:opacity-50">移除</button>
        : <span className="text-caption text-ink-muted">头像（选填）</span>}
      {error ? <p role="alert" className="m-0 text-body-sm text-danger-text">{error}</p> : null}
    </div>
  );
}
