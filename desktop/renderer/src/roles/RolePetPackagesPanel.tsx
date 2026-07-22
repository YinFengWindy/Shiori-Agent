import { toFileUrl } from "../shared/format";
import { DeleteIcon, UploadIcon } from "../shared/icons";
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
              "relative overflow-hidden rounded-md border bg-white",
              role?.selected_pet_package_id === item.id ? "border-primary ring-2 ring-primary/20" : "border-[#E2E6EB]",
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
              <span className="relative block aspect-[12/13] w-full overflow-hidden bg-[#F2F5F8]">
                <img
                  className="absolute left-0 top-0 max-w-none"
                  style={{ width: "800%", height: "900%" }}
                  src={toFileUrl(item.spritesheet_abs)}
                  alt={item.display_name}
                />
              </span>
              <span className="min-w-0 truncate text-xs text-[#32363C]">{item.display_name}</span>
            </button>
            <button
              className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-md border border-black/10 bg-white/92 text-[#8B4B4B] shadow-sm transition hover:bg-[#FFF3F3] focus:outline-none"
              type="button"
              aria-label={`删除桌宠素材 ${item.display_name}`}
              disabled={disabled}
              onClick={() => onRemove(item.id)}
            >
              <DeleteIcon className="h-3.5 w-3.5 fill-current" />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
