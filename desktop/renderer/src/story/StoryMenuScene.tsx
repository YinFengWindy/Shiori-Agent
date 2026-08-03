import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { STORY_MENU_BACKGROUND_URL, STORY_TITLE_LOGO_URL } from "./storyStaticAssets";
import { DEFAULT_STORY_MENU_THEME, type StoryMenuTheme } from "./storyMenuTheme";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

/** Fallback scene data used by isolated launcher and loading-screen renders. */
export const DEFAULT_STORY_MENU_BACKGROUND: StoryMenuBackground = {
  url: STORY_MENU_BACKGROUND_URL,
  theme: DEFAULT_STORY_MENU_THEME,
};

/** Motion and color state shared by the Story launcher scene surfaces. */
export type StoryMenuSceneState = {
  reducedMotion: boolean;
  theme: StoryMenuTheme;
};

type StoryMenuSceneProps = {
  background?: StoryMenuBackground;
  dataTestId: string;
  ariaBusy?: boolean;
  children: (state: StoryMenuSceneState) => ReactNode;
};

/** Renders the shared Story backdrop and title treatment around a scene-specific rail. */
export function StoryMenuScene({ background = DEFAULT_STORY_MENU_BACKGROUND, dataTestId, ariaBusy, children }: StoryMenuSceneProps) {
  const reducedMotion = useReducedMotion() ?? false;

  return (
    <section className="relative h-full min-h-0 overflow-hidden bg-[#1D1520]" data-testid={dataTestId} aria-busy={ariaBusy}>
      <motion.div className="absolute inset-0 bg-cover bg-center bg-no-repeat" data-testid="story-menu-backdrop" initial={{ opacity: 0, scale: reducedMotion ? 1 : 1.06 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: reducedMotion ? 0 : 1.4, ease: "easeOut" }} style={{ backgroundImage: `url(${background.url})` }} />
      <motion.header className="absolute left-[clamp(12px,2vw,28px)] top-[clamp(12px,2vh,28px)] z-10 w-[min(18rem,calc(100vw-24px))]" data-testid="story-menu-title" initial={{ opacity: 0, y: reducedMotion ? 0 : 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reducedMotion ? 0 : 0.18, duration: reducedMotion ? 0 : 0.6, ease: "easeOut" }}><h1 className="sr-only">栞 / SHIORI</h1><div className="relative overflow-hidden"><img className="block w-full" src={STORY_TITLE_LOGO_URL} alt="" />{reducedMotion ? null : <motion.span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-0 w-10 bg-white/35 blur-md" initial={{ x: "-150%" }} animate={{ x: "850%" }} transition={{ delay: 0.95, duration: 0.9, ease: "easeInOut" }} style={{ backgroundColor: background.theme.titleHighlight }} />}</div></motion.header>
      {children({ reducedMotion, theme: background.theme })}
    </section>
  );
}
