import { CheckCircleIcon, TrashIcon } from "@phosphor-icons/react";
import { UploadIcon } from "../../../apps/desktop/renderer/src/shared/icons";
import { cx } from "../../../apps/desktop/renderer/src/shared/styles";
import type { PluginRoleAssetsComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { usePetPackages } from "./usePetPackages";

/** The plugin's package library, mounted through the role.assets contribution (it needs no host services). */
export function RolePetPackagesPanel({ roleId, disabled, client, onRoleDataChanged }: Omit<PluginRoleAssetsComponentProps, "host">) {
  const { state, busy, error, onImport, onRemove, onSelect } = usePetPackages({ roleId, disabled, client, onRoleDataChanged });

  // No role open: guessing one would let a click act on somebody else's packages.
  if (!roleId) return null;
  const locked = disabled || busy;

  return (
    <section className="border-t border-line-soft px-4 py-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-ink">桌宠素材包</div>
        <button className="grid h-8 w-8 place-items-center rounded-md border border-line-soft bg-white text-ink-secondary transition hover:bg-surface-hover focus:outline-none" type="button" aria-label="导入桌宠素材包" title="导入桌宠素材包" disabled={locked} onClick={onImport}>
          <UploadIcon className="h-4 w-4 fill-current" />
        </button>
      </div>
      {error ? <div className="mb-2 text-xs text-danger-text">{error}</div> : null}
      <div className="grid grid-cols-2 gap-2">
        {state.packages.map((item) => (
          <div
            className={cx(
              "group relative overflow-hidden rounded-md border bg-white",
              state.selectedPackageId === item.id ? "border-accent shadow-soft" : "border-line-soft",
            )}
            key={item.id}
          >
            <button
              className="grid w-full gap-2 p-2 text-left transition hover:bg-surface-hover focus:outline-none"
              type="button"
              disabled={locked}
              aria-pressed={state.selectedPackageId === item.id}
              onClick={() => onSelect(item.id)}
            >
              <span className="relative block aspect-square w-full overflow-hidden bg-surface-soft">
                {item.previewUrl ? <img className="h-full w-full object-contain" src={item.previewUrl} alt={item.displayName} /> : null}
              </span>
              <span className="min-w-0 truncate text-xs text-ink">{item.displayName}</span>
            </button>
            <button
              className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-md border border-line-soft bg-white/92 text-ink-secondary opacity-0 shadow-soft transition hover:border-[var(--danger-300)] hover:bg-danger-soft hover:text-danger-text focus:opacity-100 group-hover:opacity-100 focus:outline-none"
              type="button"
              aria-label={`删除桌宠素材 ${item.displayName}`}
              disabled={locked}
              onClick={() => onRemove(item.id)}
            >
              <TrashIcon className="h-4 w-4" weight="bold" />
            </button>
            {state.selectedPackageId === item.id ? <CheckCircleIcon className="absolute left-2 top-2 h-5 w-5 text-ink-secondary" weight="fill" aria-label="已选中" /> : null}
          </div>
        ))}
      </div>
    </section>
  );
}
