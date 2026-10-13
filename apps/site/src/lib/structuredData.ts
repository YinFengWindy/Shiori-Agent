/**
 * The site's schema.org structured data (JSON-LD): who publishes the site,
 * the site itself and the app it is about (#799). The breadcrumb trails' own
 * BreadcrumbList is in `breadcrumbs.ts`; every page writes its data through
 * `inlineJson`.
 */

import { SITE_DESCRIPTION, SITE_LINKS, SITE_NAME } from "./siteMeta";

/** JSON for an inline `<script>`: `<` escaped so no text in it can close the element. */
export function inlineJson(value: unknown): string {
  return JSON.stringify(value).replaceAll("<", "\\u003c");
}

/** `@id` of the site's publisher, the Shiori project, so other items can point at it. */
export function organizationId(site: URL): string {
  return new URL("/#organization", site).href;
}

/**
 * The Shiori project as an Organization: name, home page, logo (the app
 * icon) and its repository. A BlogPosting names it as publisher in full,
 * the home page's items by `@id`.
 */
export function organizationJsonLd(site: URL, logoPath: string) {
  return {
    "@type": "Organization",
    "@id": organizationId(site),
    name: SITE_NAME,
    url: new URL("/", site).href,
    logo: { "@type": "ImageObject", url: new URL(logoPath, site).href },
    sameAs: [SITE_LINKS.github],
  };
}

/** A release tag as a version number: `v0.5.3` → `0.5.3`. */
export function softwareVersion(tag: string): string {
  return tag.replace(/^v(?=\d)/, "");
}

/** What the home page's structured data is built from, beyond `site`. */
export interface HomeJsonLdInput {
  site: URL;
  /** Site path of the app icon: the Organization's logo. */
  logoPath: string;
  /** Site path of the home page's share picture. */
  imagePath: string;
  /** The latest published release, read at build time (`lib/changelog.ts`). */
  release: { version: string; publishedAt: Date };
}

/**
 * The home page's JSON-LD (#799), one `@graph`: the WebSite, its publisher
 * (the Organization) and the app as a free Windows SoftwareApplication — the
 * latest release's version and day, the latest-release page as its download.
 */
export function homeJsonLd({ site, logoPath, imagePath, release }: HomeJsonLdInput) {
  const home = new URL("/", site).href;
  const publisher = { "@id": organizationId(site) };
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": new URL("/#website", site).href,
        name: SITE_NAME,
        url: home,
        description: SITE_DESCRIPTION,
        inLanguage: "zh-CN",
        publisher,
      },
      organizationJsonLd(site, logoPath),
      {
        "@type": "SoftwareApplication",
        "@id": new URL("/#software", site).href,
        name: SITE_NAME,
        description: SITE_DESCRIPTION,
        url: home,
        image: new URL(imagePath, site).href,
        operatingSystem: "Windows",
        // A companion that lives on the desktop: closest of schema.org's app categories.
        applicationCategory: "LifestyleApplication",
        inLanguage: "zh-CN",
        isAccessibleForFree: true,
        offers: { "@type": "Offer", price: "0", priceCurrency: "CNY" },
        downloadUrl: SITE_LINKS.releasesLatest,
        softwareVersion: softwareVersion(release.version),
        dateModified: release.publishedAt.toISOString(),
        license: SITE_LINKS.license,
        author: publisher,
        publisher,
      },
    ],
  };
}
