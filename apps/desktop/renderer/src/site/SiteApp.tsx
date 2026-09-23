/** Relative to the built site's own output root (see vite.site.config.ts), not the desktop renderer's. */
const SITE_LOGO_URL = "./assets/branding/shiori-title-logo.png";

/**
 * Static site skeleton entry: shows only the Shiori brand wordmark and a
 * placeholder title. Later tickets build the real galgame-style landing
 * site on top of this shell (see #345). Deliberately has no desktop
 * business components, host bridge, or backend dependency.
 */
export function SiteApp() {
  return (
    <div className="bg-gradient-app grid h-dvh min-h-0 place-items-center px-6 text-center text-ink">
      <div className="flex flex-col items-center gap-6">
        <h1 className="sr-only">栞 / SHIORI</h1>
        <img className="w-[min(18rem,70vw)]" src={SITE_LOGO_URL} alt="" />
        <p className="font-display text-title text-ink-secondary">敬请期待</p>
      </div>
    </div>
  );
}
