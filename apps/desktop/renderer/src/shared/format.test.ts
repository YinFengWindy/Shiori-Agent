/// <reference types="node" />

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { formatClock, formatDate, formatHourMinute, formatTimestamp, parseTimestamp, toFileUrl } from "./format";

describe("parseTimestamp", () => {
  it("reads naive date-times and bare dates as local wall-clock time", () => {
    const naive = parseTimestamp("2026-09-01T08:30:00");
    assert.deepEqual([naive?.getFullYear(), naive?.getMonth(), naive?.getDate(), naive?.getHours(), naive?.getMinutes()], [2026, 8, 1, 8, 30]);
    const bare = parseTimestamp("2026-09-01");
    assert.deepEqual([bare?.getDate(), bare?.getHours()], [1, 0]);
  });

  it("keeps the instant of offset-bearing values and rejects invalid input", () => {
    assert.equal(parseTimestamp("2026-09-01T00:00:00+00:00")?.getTime(), Date.UTC(2026, 8, 1));
    assert.equal(parseTimestamp("not a time"), null);
    assert.equal(parseTimestamp(""), null);
  });

  it("formats nothing for missing or invalid values", () => {
    for (const format of [formatTimestamp, formatDate, formatClock]) {
      assert.equal(format(undefined), "");
      assert.equal(format("not a time"), "");
    }
    assert.notEqual(formatClock("2026-09-01T08:30:00"), "");
  });
});

describe("toFileUrl", () => {
  it("fails closed when the desktop preload boundary is unavailable", () => {
    assert.equal(
      toFileUrl("C:\\private\\secret.png"),
      "shiori-asset://local/unavailable",
    );
  });

  it("returns the opaque token URL from the desktop resolver unchanged", () => {
    const absolutePath = "C:\\Users\\yufeng\\My Avatars\\头像 #1.png";
    const opaqueUrl = "shiori-asset://local/token-2fR9dQ";
    let resolvedPath = "";

    const result = toFileUrl(absolutePath, (path) => {
      resolvedPath = path;
      return opaqueUrl;
    });

    assert.equal(resolvedPath, absolutePath);
    assert.equal(result, opaqueUrl);
    assert.equal(result.includes(absolutePath), false);
  });

  it("does not encode or embed POSIX paths before resolving them", () => {
    const absolutePath = "/Users/yufeng/My Avatars/头像 #1.png";
    const opaqueUrl = "shiori-asset://local/token-k8Lm3P";

    const result = toFileUrl(absolutePath, (path) => {
      assert.equal(path, absolutePath);
      assert.equal(path.includes("%2F"), false);
      return opaqueUrl;
    });

    assert.equal(result, opaqueUrl);
    assert.equal(result.includes(absolutePath), false);
  });
});

describe("formatHourMinute", () => {
  it("is local 24-hour time with padded hours and minutes", () => {
    assert.equal(formatHourMinute(new Date(2026, 8, 29, 7, 5)), "07:05");
    assert.equal(formatHourMinute(new Date(2026, 8, 29, 23, 59)), "23:59");
  });
});
