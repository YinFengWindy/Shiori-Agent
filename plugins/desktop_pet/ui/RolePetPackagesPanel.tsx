import { useRef, useState } from "react";
import { CheckCircleIcon, TrashIcon } from "@phosphor-icons/react";
import { compactGhostButtonClass, compactPressableClass, cx, iconButtonClass, PetalIcon, UploadIcon, usePluginHostServices, type PluginRoleAssetsComponentProps } from "@yinfengwindy/shiori-sdk";
import type { PetPackageRow } from "./petPackages";
import { usePetPackages } from "./usePetPackages";
import { petModelKey } from "../provider";

/** The 24px bordered delete tile on a package card; always shown, so keyboard and touch users reach it. */
const removeButtonClass = cx(
  compactPressableClass,
  "grid h-6 w-6 place-items-center rounded-md border border-line-soft bg-surface text-ink-secondary shadow-soft hover:border-danger/40 hover:bg-danger-soft hover:text-danger-text disabled:cursor-default disabled:opacity-50",
);

type PetPackageCardProps = {
  item: PetPackageRow;
  selected: boolean;
  locked: boolean;
  onSelect: () => void;
  onRemove: () => void;
};

/** One package: the card selects it, the corner button asks to delete it. */
function PetPackageCard({ item, selected, locked, onSelect, onRemove }: PetPackageCardProps) {
  return (
    <div className={cx("relative overflow-hidden rounded-md border bg-surface", selected ? "border-accent shadow-soft" : "border-line-soft")}>
      <button
        className="grid w-full gap-1.5 p-1.5 text-left transition-colors hover:bg-surface-hover disabled:cursor-default"
        type="button"
        disabled={locked}
        aria-pressed={selected}
        onClick={onSelect}
      >
        <span className="relative block aspect-square w-full overflow-hidden rounded-sm bg-surface-soft">
          {item.previewUrl ? <img className="h-full w-full object-contain" src={item.previewUrl} alt={item.displayName} /> : null}
        </span>
        <span className="min-w-0 truncate text-caption text-ink">{item.displayName}</span>
      </button>
      <button className={cx(removeButtonClass, "absolute right-1 top-1")} type="button" aria-label={`删除桌宠素材 ${item.displayName}`} disabled={locked} onClick={onRemove}>
        <TrashIcon className="h-3.5 w-3.5" weight="bold" />
      </button>
      {selected ? <CheckCircleIcon className="absolute left-1 top-1 h-4 w-4 text-accent" weight="fill" aria-label="已选中" /> : null}
    </div>
  );
}

/** The plugin's package library, mounted through the role.assets contribution. */
export function RolePetPackagesPanel({ roleId, disabled, client, onRoleDataChanged }: Omit<PluginRoleAssetsComponentProps, "host">) {
  const host = usePluginHostServices();
  const { state, loading, busy, error, onImport, onRemove, onSelect } = usePetPackages({ roleId, disabled, client, onRoleDataChanged });
  const [pendingRemoval, setPendingRemoval] = useState<PetPackageRow | null>(null);
  // Focus lands here once the deleted card (the dialog's trigger) is gone.
  const importButton = useRef<HTMLButtonElement>(null);

  // No role open: guessing one would let a click act on somebody else's packages.
  if (!roleId) return null;
  const locked = disabled || busy;
  const selectedProviderUnavailable = state.selectedModel !== null && !state.providers.some((provider) => (
    provider.reference.plugin_id === state.selectedModel?.provider.plugin_id
    && provider.reference.service_id === state.selectedModel?.provider.service_id
  ));

  const confirmRemoval = async () => {
    if (!pendingRemoval) return;
    await onRemove(pendingRemoval.reference);
    setPendingRemoval(null);
  };

  return (
    <section className="border-t border-line-soft px-4 py-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="m-0 text-body-sm font-medium text-ink">桌宠素材包</h3>
        <div className="flex items-center gap-2">
          {state.providers.map((provider, index) => (
            <button key={`${provider.reference.plugin_id}/${provider.reference.service_id}`} ref={index === 0 ? importButton : undefined}
              className={state.providers.length === 1 ? iconButtonClass : compactGhostButtonClass} type="button"
              aria-label={state.providers.length === 1 ? "导入桌宠素材包" : `导入${provider.label}素材包`}
              title={`导入${provider.label}素材包`} disabled={locked} onClick={() => onImport(provider)}>
              <UploadIcon className="h-4 w-4 fill-current" />
              {state.providers.length > 1 ? <span>{provider.label}</span> : null}
            </button>
          ))}
        </div>
      </div>
      {error ? <host.ui.InlineError className="mb-2" {...error} /> : null}
      {selectedProviderUnavailable ? <host.ui.InlineError className="mb-2" message="当前形象插件不可用" /> : null}
      {loading ? (
        <p role="status" className="m-0 text-body-sm text-ink-muted">正在读取…</p>
      ) : state.packages.length === 0 ? (
        <div className="grid place-items-center gap-1.5 rounded-md border border-dashed border-line-soft px-4 py-6 text-caption text-ink-muted">
          <PetalIcon className="h-5 w-5 text-accent" />
          {state.providers.length ? "暂无桌宠素材包" : "暂无可用形象插件"}
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-2.5">
          {state.packages.map((item) => (
            <PetPackageCard
              key={petModelKey(item.reference)}
              item={item}
              selected={state.selectedModel !== null && petModelKey(state.selectedModel) === petModelKey(item.reference)}
              locked={locked}
              onSelect={() => onSelect(item.reference)}
              onRemove={() => setPendingRemoval(item)}
            />
          ))}
        </div>
      )}
      <host.ui.ConfirmDialog
        open={Boolean(pendingRemoval)}
        persona="destructive"
        destructive
        title="删除桌宠素材包"
        description={pendingRemoval ? `“${pendingRemoval.displayName}” 删除后无法恢复。` : ""}
        confirmLabel="删除"
        busy={busy}
        finalFocus={importButton}
        onClose={() => setPendingRemoval(null)}
        onConfirm={() => void confirmRemoval()}
      />
    </section>
  );
}
