import { emptyPetReply, readPresentationState, type PetProviderLoad, type PetPresentationIdentity } from "@shiori-plugin/desktop_pet/provider";
import { array, finite, record, text } from "../surface/runtime/model";

/** Provider-private model documents and authorized image URLs in retained state. */
export type AvatarPresentation = PetProviderLoad & { model_data: Record<string, unknown> };
/** Converts granted backend image paths to URLs before any surface sees them. */
export function prepareAvatar(identity: PetPresentationIdentity, value: Record<string, unknown>, assetUrl: (path: string) => string | null): AvatarPresentation {
  const body = record(value.body), width = finite(body.width), height = finite(body.height);
  if (width <= 0 || height <= 0 || width > 2048 || height > 2048) throw new Error("2.5D 显示尺寸无效");
  const data = record(value.model_data);
  const images = array(data.images).map((value) => { const image = record(value), file = text(image.file), url = assetUrl(text(image.image_path)); if (!url) throw new Error(`2.5D 图片未获授权 ${file}`); return { file, url }; });
  const state = value.state === undefined ? { reply: emptyPetReply, voice: { status: "idle" as const } } : readPresentationState(value.state);
  if (!state) throw new Error("2.5D 展示状态无效");
  return { ...identity, body: { width, height }, state, model_data: { ...data, images } };
}
