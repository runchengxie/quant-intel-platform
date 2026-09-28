const test = require("node:test");
const assert = require("node:assert/strict");
const { normalizeTheme, nextTheme } = require("../src/legacy/theme-utils.js");

test("theme preference cycles through system, light, and dark", () => {
  assert.equal(normalizeTheme("unknown"), "system");
  assert.equal(nextTheme("system"), "light");
  assert.equal(nextTheme("light"), "dark");
  assert.equal(nextTheme("dark"), "system");
});
