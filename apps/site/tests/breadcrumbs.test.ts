import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { breadcrumbListJsonLd, homeCrumb } from "../src/lib/breadcrumbs";

const SITE = new URL("https://www.windchant.online");

describe("homeCrumb", () => {
  it("leads to the download state of the home page in the trail's language (#806)", () => {
    assert.deepEqual(homeCrumb("zh"), { label: "首页", href: "/#download" });
    assert.deepEqual(homeCrumb("en"), { label: "Home", href: "/en/#download" });
  });
});

describe("breadcrumbListJsonLd", () => {
  it("numbers the steps from 1 with absolute URLs, the home step without its in-page anchor", () => {
    assert.deepEqual(breadcrumbListJsonLd([homeCrumb("zh"), { label: "博客", href: "/blog/" }], SITE).itemListElement, [
      { "@type": "ListItem", position: 1, name: "首页", item: "https://www.windchant.online/" },
      { "@type": "ListItem", position: 2, name: "博客", item: "https://www.windchant.online/blog/" },
    ]);
    assert.equal(breadcrumbListJsonLd([homeCrumb("en")], SITE).itemListElement[0]?.item, "https://www.windchant.online/en/");
  });

  it("rejects an empty trail", () => {
    assert.throws(() => breadcrumbListJsonLd([], SITE));
  });
});
