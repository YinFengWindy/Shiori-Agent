/**
 * Search engines' site-ownership checks (#799): each webmaster console
 * (Google Search Console, Bing Webmaster Tools, 百度搜索资源平台) hands out a
 * public token to serve in a `<meta>` on the site. Baidu's token is included
 * here so normal deployments can verify the site without extra setup.
 * Build environment variables can override tokens; an empty value omits its tag.
 */

/** The build environment, as far as the verification tags read it. */
export interface SiteVerificationEnv {
  SITE_VERIFY_GOOGLE?: string;
  SITE_VERIFY_BING?: string;
  SITE_VERIFY_BAIDU?: string;
}

/** Each engine's optional override, public default token and `<meta name>`. */
const VERIFICATION_TAGS = [
  { variable: "SITE_VERIFY_GOOGLE", name: "google-site-verification", defaultToken: "" },
  { variable: "SITE_VERIFY_BING", name: "msvalidate.01", defaultToken: "" },
  { variable: "SITE_VERIFY_BAIDU", name: "baidu-site-verification", defaultToken: "codeva-DEC4knpJlo" },
] as const;

/** The verification tags from public defaults and build environment overrides. */
export function siteVerificationMeta(env: SiteVerificationEnv): { name: string; content: string }[] {
  return VERIFICATION_TAGS.flatMap(({ variable, name, defaultToken }) => {
    const content = (env[variable] ?? defaultToken).trim();
    return content ? [{ name, content }] : [];
  });
}
