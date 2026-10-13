import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  hreflangLinks,
  languageSwitchHref,
  localeHome,
  localePath,
  otherLocale,
  versionFor,
  withXDefault,
} from "../src/i18n/locales";

const SITE = new URL("https://www.windchant.online");

describe("localePath", () => {
  it("keeps Chinese paths at the root and puts English ones under /en/", () => {
    assert.equal(localePath("zh", "/blog/"), "/blog/");
    assert.equal(localePath("en", "/blog/"), "/en/blog/");
    assert.equal(localeHome("zh"), "/");
    assert.equal(localeHome("en"), "/en/");
  });

  it("rejects a relative path", () => {
    assert.throws(() => localePath("en", "blog/"));
  });
});

describe("versionFor", () => {
  it("takes the page in the reader's language, else the Chinese one", () => {
    assert.equal(versionFor("en", { zh: "/blog/", en: "/en/blog/" }), "/en/blog/");
    assert.equal(versionFor("en", { zh: "/blog/" }), "/blog/");
    assert.equal(versionFor("zh", { zh: "/blog/" }), "/blog/");
  });
});

describe("languageSwitchHref", () => {
  it("leads to the same page in the other language", () => {
    assert.equal(otherLocale("zh"), "en");
    assert.equal(languageSwitchHref("zh", { zh: "/", en: "/en/" }), "/en/");
    assert.equal(languageSwitchHref("en", { zh: "/", en: "/en/" }), "/");
  });

  it("leads to the other language's home page when the page has no version in it", () => {
    assert.equal(languageSwitchHref("zh", { zh: "/blog/some-post/" }), "/en/");
  });
});

describe("hreflangLinks", () => {
  it("pairs a page in both languages, itself included, with x-default on the Chinese page", () => {
    assert.deepEqual(hreflangLinks({ zh: "/", en: "/en/" }, SITE), [
      { hreflang: "zh-CN", href: "https://www.windchant.online/" },
      { hreflang: "en", href: "https://www.windchant.online/en/" },
      { hreflang: "x-default", href: "https://www.windchant.online/" },
    ]);
  });

  it("claims no alternate for a page in one language only (#807: a post without its English version)", () => {
    assert.deepEqual(hreflangLinks({ zh: "/blog/some-post/" }, SITE), []);
  });
});

describe("withXDefault", () => {
  it("adds x-default on the Chinese page to a sitemap entry's language pair", () => {
    const item = {
      url: "https://www.windchant.online/en/",
      links: [
        { url: "https://www.windchant.online/", lang: "zh-CN" },
        { url: "https://www.windchant.online/en/", lang: "en" },
      ],
    };
    assert.deepEqual(withXDefault(item).links, [...item.links, { url: "https://www.windchant.online/", lang: "x-default" }]);
  });

  it("leaves an entry without alternates as it is", () => {
    const item = { url: "https://www.windchant.online/blog/" };
    assert.equal(withXDefault(item), item);
  });
});
