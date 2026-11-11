import type { NativeFilePickerOptions, PluginServiceReference } from "@yinfengwindy/shiori-sdk";
import { isRecord } from "../provider/guards";
import { readPetModelReference, readPetProviderReference, type PetModelReference } from "../provider";

/** A model offered by one installed appearance provider. */
export type PetPackageRow = {
  reference: PetModelReference;
  displayName: string;
  previewUrl: string;
};

/** Import policy is supplied by the plugin that validates and owns the files. */
export type PetPackageProvider = {
  reference: PluginServiceReference;
  label: string;
  importOptions: NativeFilePickerOptions;
};

/** The role's saved selection and models from currently available providers. */
export type PetPackages = {
  selectedModel: PetModelReference | null;
  packages: PetPackageRow[];
  providers: PetPackageProvider[];
};

export const noPetPackages: PetPackages = { selectedModel: null, packages: [], providers: [] };

/** Reads the provider-scoped library, converting granted paths to opaque URLs. */
export function readPetPackages(value: unknown, resolveAssetUrl: (path: string) => string): PetPackages {
  if (!isRecord(value) || !Array.isArray(value.packages) || !Array.isArray(value.providers)) {
    throw new Error("桌宠素材列表格式无效");
  }
  const packages = value.packages.map((row): PetPackageRow => {
    if (!isRecord(row)) throw new Error("桌宠素材记录格式无效");
    const reference = readPetModelReference({ provider: row.provider, model_id: row.id });
    if (!reference || typeof row.display_name !== "string") throw new Error("桌宠素材缺少提供者或名称");
    return {
      reference,
      displayName: row.display_name,
      previewUrl: typeof row.preview_abs === "string" && row.preview_abs ? resolveAssetUrl(row.preview_abs) : "",
    };
  });
  const providers = value.providers.map((provider): PetPackageProvider => {
    if (!isRecord(provider) || typeof provider.label !== "string") throw new Error("形象插件记录格式无效");
    const reference = readPetProviderReference(provider);
    const policy = provider.import;
    if (!reference || !isRecord(policy) || typeof policy.namespace !== "string" || !policy.namespace
      || typeof policy.max_file_bytes !== "number" || !Number.isSafeInteger(policy.max_file_bytes) || policy.max_file_bytes <= 0
      || typeof policy.label !== "string" || !Array.isArray(policy.extensions) || !policy.extensions.length
      || !policy.extensions.every((extension): extension is string => typeof extension === "string" && /^[a-z0-9]+$/i.test(extension))) {
      throw new Error("形象插件导入配置无效");
    }
    return {
      reference,
      label: provider.label,
      importOptions: {
        namespace: policy.namespace,
        filters: [{ name: policy.label, extensions: policy.extensions }],
        multiple: false,
        maxFileBytes: policy.max_file_bytes,
      },
    };
  });
  const selectedModel = value.selected_model == null ? null : readPetModelReference(value.selected_model);
  if (value.selected_model != null && !selectedModel) throw new Error("桌宠已选形象格式无效");
  return { selectedModel, packages, providers };
}
