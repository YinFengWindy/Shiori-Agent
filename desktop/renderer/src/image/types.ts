export type ImageMode = "txt2img" | "img2img";
export type ImageSizePreset = "square" | "landscape" | "portrait" | "custom";

export type ImageStudioFormState = {
  roleId: string;
  prompt: string;
  negativePrompt: string;
  mode: ImageMode;
  baseImagePath: string;
  sizePreset: ImageSizePreset;
  customWidth: string;
  customHeight: string;
  steps: string;
  seed: string;
  sampler: string;
  strength: string;
  noise: string;
  model: string;
};

export type ImageHistoryRecord = {
  id: string;
  created_at: string;
  role_id: string;
  session_key: string;
  mode: ImageMode;
  prompt: string;
  negative_prompt: string;
  model: string;
  sampler: string;
  steps: number;
  seed: number | null;
  width: number;
  height: number;
  base_image_path: string;
  output_paths: string[];
  wrote_back_to_role: boolean;
  role_asset_paths: string[];
};

export type ImageGenerateResult = {
  record_id: string;
  created_at: string;
  mode: ImageMode;
  model: string;
  seed: number | null;
  width: number;
  height: number;
  output_paths: string[];
  request_path: string;
  meta_path: string;
  wrote_back_to_role: boolean;
  role_asset_paths: string[];
  message?: string;
};
