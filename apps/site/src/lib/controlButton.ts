import { cx, iconButtonClass } from "@yinfengwindy/shiori-sdk";

/**
 * The look of the home page's two small controls (#810), the music switch
 * (SoundToggle.tsx, an icon) and the language switch (LanguageSwitch.astro,
 * 「EN」 / 「中」), wherever they sit — side by side in the corner, and in
 * the top bar: one square icon-button tile, so the two match in size,
 * corners, border, fill, colour and their hover, press and focus states.
 * The type is for the language switch's short label, a medium weight that
 * sits with the icon's stroke. That switch is a link, which `:enabled` never
 * matches: `active:scale-97` gives it the button's press, and
 * `no-underline` drops the link underline.
 */
export const controlButtonClass = cx(iconButtonClass, "text-body-sm font-medium no-underline motion-safe:active:scale-97");
