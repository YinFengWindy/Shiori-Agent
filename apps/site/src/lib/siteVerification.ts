/**
 * Search engines' site-ownership checks (#799): each webmaster console
 * (Google Search Console, Bing Webmaster Tools, 百度搜索资源平台) hands out a
 * token to serve in a `<meta>` on the site. The tokens come from the build's
 * environment, so the deployment holds them and the repository does not; an
 * engine whose variable is unset or empty gets no tag.
 */

/** The build environment, as far as the verification tags read it. */
export interface SiteVerificationEnv {
  SITE_VERIFY_GOOGLE?: string;
  SITE_VERIFY_BING?: string;
  SITE_VERIFY_BAIDU?: string;
}

/** Each engine's variable and the `<meta name>` its token goes in. */
const VERIFICATION_TAGS = [
  { variable: "SITE_VERIFY_GOOGLE", name: "google-site-verification" },
  { variable: "SITE_VERIFY_BING", name: "msvalidate.01" },
  { variable: "SITE_VERIFY_BAIDU", name: "baidu-site-verification" },
] as const;

/** The verification `<meta>` tags to emit, as name and content, for the engines `env` has a token for. */
export function siteVerificationMeta(env: SiteVerificationEnv): { name: string; content: string }[] {
  return VERIFICATION_TAGS.flatMap(({ variable, name }) => {
    const content = env[variable]?.trim();
    return content ? [{ name, content }] : [];
  });
}
