import type { PetBinding, PetModelReference } from "@yinfengwindy/shiori-pet";
/** Resolved provider-neutral desktop pet binding. */
export type DesktopPetBinding = PetBinding;
/** Device-local window position. */
export type DesktopPetPosition = { x: number; y: number };
/** Desktop-owned selection mirror and device positions; models belong to providers. */
export type DesktopPetSettings = { visible: boolean; roleId: string | null; model: PetModelReference | null; positions: Record<string, DesktopPetPosition> };
