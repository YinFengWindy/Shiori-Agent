import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { HOME_CRUMB, breadcrumbListJsonLd } from "../src/lib/breadcrumbs";

const SITE = new URL("https://www.windchant.online");

describe("breadcrumbListJsonLd", () => {
  it("numbers the steps from 1 with absolute URLs, the home step without its in-page anchor", () => {
    assert.equal(HOME_CRUMB.href, "/#download");
    assert.deepEqual(breadcrumbListJsonLd([HOME_CRUMB, { label: "博客", href: "/blog/" }], SITE).itemListElement, [
      { "@type": "ListItem", position: 1, name: "首页", item: "https://www.windchant.online/" },
      { "@type": "ListItem", position: 2, name: "博客", item: "https://www.windchant.online/blog/" },
    ]);
  });

  it("rejects an empty trail", () => {
    assert.throws(() => breadcrumbListJsonLd([], SITE));
  });
});
