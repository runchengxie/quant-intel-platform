const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const css = fs.readFileSync(path.join(__dirname, "../src/legacy/styles.css"), "utf8");

function palette(selector) {
  const start = css.indexOf(`${selector} {`);
  assert.notEqual(start, -1, `${selector} palette exists`);
  const block = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries(
    [...block.matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-f]{6})\s*;/gi)].map(
      ([, name, color]) => [name, color.toLowerCase()]
    )
  );
}

function rgb(hex) {
  return [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16));
}

function luminance(hex) {
  const [red, green, blue] = rgb(hex).map((value) => {
    const channel = value / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return red * 0.2126 + green * 0.7152 + blue * 0.0722;
}

function contrast(first, second) {
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

test("light and dark themes use a legible unified warm palette", () => {
  for (const selector of [":root", ':root[data-theme="dark"]']) {
    const colors = palette(selector);
    for (const token of ["--accent", "--brand", "--ink", "--paper", "--muted", "--accent-on"]) {
      assert.ok(colors[token], `${selector} defines ${token}`);
    }
    for (const token of ["--paper", "--card", "--line", "--accent", "--accent-pale", "--brand", "--health-bg", "--health-ink"]) {
      const [red, green, blue] = rgb(colors[token]);
      assert.ok(red > green && green > blue, `${selector} ${token} stays warm`);
    }
    assert.ok(contrast(colors["--ink"], colors["--paper"]) >= 7, `${selector} primary text is legible`);
    assert.ok(contrast(colors["--muted"], colors["--paper"]) >= 4.5, `${selector} secondary text is legible`);
    assert.ok(contrast(colors["--accent-on"], colors["--accent"]) >= 4.5, `${selector} active controls are legible`);
    assert.ok(contrast(colors["--card"], colors["--brand"]) >= 4.5, `${selector} brand mark is legible`);
  }
  assert.deepEqual(
    palette(':root:not([data-theme="light"])'),
    palette(':root[data-theme="dark"]'),
    "system dark mode matches the selected dark palette"
  );
});
