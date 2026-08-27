import { toFileUrl } from "../shared/format";
import { CheckCircleIcon, TrashIcon } from "@phosphor-icons/react";
import { UploadIcon } from "../shared/icons";
import { cx } from "../shared/styles";
import type { RoleRecord } from "../shared/types";

type RolePetPackagesPanelProps = {
  role: RoleRecord | null;
  disabled: boolean;
  onImport: () => void;
  onRemove: (packageId: string) => void;
  onSelect: (packageId: string) => void;
};

/** Manages desktop-pet packages inside the owning role's asset library. */
export function RolePetPackagesPanel({ role, disabled, onImport, onRemove, onSelect }: RolePetPackagesPanelProps) {
  const packages = role?.pet_packages ?? [];
  return (
    <section className="border-t border-[#E4EAF0] px-4 py-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-[#2A3440]">桌宠素材包</div>
        <button className="grid h-8 w-8 place-items-center rounded-md border border-[#D8DFE7] bg-white text-[#5B6472] transition hover:bg-[#F4F6F8] focus:outline-none" type="button" aria-label="导入桌宠素材包" title="导入桌宠素材包" disabled={disabled} onClick={onImport}>
          <UploadIcon className="h-4 w-4 fill-current" />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {packages.map((item) => (
          <div
            className={cx(
              "group relative overflow-hidden rounded-md border bg-white",
              role?.selected_pet_package_id === item.id ? "border-[#4B5563] shadow-[0_2px_8px_rgba(15,23,42,0.12)]" : "border-[#E2E6EB]",
            )}
            key={item.id}
          >
            <button
              className="grid w-full gap-2 p-2 text-left transition hover:bg-[#F7F9FB] focus:outline-none"
              type="button"
              disabled={disabled}
              aria-pressed={role?.selected_pet_package_id === item.id}
              onClick={() => onSelect(item.id)}
            >
              <span className="relative block aspect-square w-full overflow-hidden bg-[#F2F5F8]">
                {item.preview_abs ? <img className="h-full w-full object-contain" src={toFileUrl(item.preview_abs)} alt={item.display_name} /> : null}
              </span>
              <span className="min-w-0 truncate text-xs text-[#32363C]">{item.display_name}</span>
            </button>
            <button
              className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-md border border-black/10 bg-white/92 text-[#5B6472] opacity-0 shadow-sm transition hover:border-[#E0B8B8] hover:bg-white hover:text-[#9A4A4A] focus:opacity-100 group-hover:opacity-100 focus:outline-none"
              type="button"
              aria-label={`删除桌宠素材 ${item.display_name}`}
              disabled={disabled}
              onClick={() => onRemove(item.id)}
            >
              <TrashIcon className="h-4 w-4" weight="bold" />
            </button>
            {role?.selected_pet_package_id === item.id ? <CheckCircleIcon className="absolute left-2 top-2 h-5 w-5 text-[#374151]" weight="fill" aria-label="已选中" /> : null}
          </div>
        ))}
      </div>
    </section>
  );
}
