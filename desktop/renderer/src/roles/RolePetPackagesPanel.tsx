import { UploadIcon } from "../shared/icons";
import type { RoleRecord } from "../shared/types";

type RolePetPackagesPanelProps = {
  role: RoleRecord | null;
  disabled: boolean;
  onImport: () => void;
  onRemove: (packageId: string) => void;
};

/** Manages desktop-pet packages inside the owning role's asset library. */
export function RolePetPackagesPanel({ role, disabled, onImport, onRemove }: RolePetPackagesPanelProps) {
  const packages = role?.pet_packages ?? [];
  return (
    <section className="border-t border-[#E4EAF0] px-4 py-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-[#2A3440]">桌宠素材包</div>
        <button className="grid h-8 w-8 place-items-center rounded-md border border-[#D8DFE7] bg-white text-[#5B6472] transition hover:bg-[#F4F6F8] focus:outline-none" type="button" aria-label="导入桌宠素材包" title="导入桌宠素材包" disabled={disabled} onClick={onImport}>
          <UploadIcon className="h-4 w-4 fill-current" />
        </button>
      </div>
      <div className="grid gap-2">
        {packages.map((item) => (
          <div className="flex items-center justify-between rounded-md border border-[#E2E6EB] bg-white px-3 py-2" key={item.id}>
            <span className="min-w-0 truncate text-sm text-[#32363C]">{item.display_name}</span>
            <button className="rounded-md px-2 py-1 text-xs text-[#9A4A4A] transition hover:bg-[#FFF3F3] focus:outline-none" type="button" disabled={disabled} onClick={() => onRemove(item.id)}>删除</button>
          </div>
        ))}
      </div>
    </section>
  );
}
