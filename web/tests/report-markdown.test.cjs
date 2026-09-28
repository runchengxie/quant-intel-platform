const test = require("node:test");
const assert = require("node:assert/strict");
const reports = require("../artifacts/public/data/reports.json").reports;
const { renderReportBlocks } = require("../src/legacy/report-markdown.js");

function element(tagName) {
  return {
    tagName,
    children: [],
    className: "",
    _text: "",
    append(...children) { this.children.push(...children); },
    set textContent(value) { this._text = value; this.children = []; },
    get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); },
  };
}

const document = { createElement: element };

test("renders six-dimensional pipe rows as a table with alignment and cell text", () => {
  const nodes = renderReportBlocks(document, [
    "| 维度 | 观察分 | 状态 | 证据 |",
    "|---|---:|---|---|",
    "| 流动性 | 78.7 | 较强 | 成交额 1.11x |",
    "| 广度 | 78.5 | 较强 | 上涨率 76.2% |",
  ]);
  assert.deepEqual(nodes.map((node) => node.tagName), ["div"]);
  const table = nodes[0].children[0];
  assert.equal(table.tagName, "table");
  assert.deepEqual(table.children.map((node) => node.tagName), ["thead", "tbody"]);
  assert.deepEqual(table.children[0].children[0].children.map((cell) => cell.textContent), ["维度", "观察分", "状态", "证据"]);
  assert.equal(table.children[0].children[0].children[1].className, "is-numeric");
  assert.deepEqual(table.children[1].children.map((row) => row.children.map((cell) => cell.textContent)), [
    ["流动性", "78.7", "较强", "成交额 1.11x"],
    ["广度", "78.5", "较强", "上涨率 76.2%"],
  ]);
});

test("renders list, heading and following text as distinct blocks", () => {
  const nodes = renderReportBlocks(document, [
    "- 状态: 偏热。", "- 热度: 88.1。", "### 后续观察", "1. 核对成交额", "2. 核对广度", "结论待定。",
  ]);
  assert.deepEqual(nodes.map((node) => node.tagName), ["ul", "h5", "ol", "p"]);
  assert.deepEqual(nodes[0].children.map((node) => node.textContent), ["状态: 偏热。", "热度: 88.1。"]);
  assert.equal(nodes[1].textContent, "后续观察");
  assert.deepEqual(nodes[2].children.map((node) => node.textContent), ["核对成交额", "核对广度"]);
  assert.equal(nodes[3].textContent, "结论待定。");
});

test("keeps ordinary pipes as text and treats HTML from a report as literal text", () => {
  const nodes = renderReportBlocks(document, [
    "上涨 4234 家 | 下跌 1152 家", "| 假表头 | 观察分 |", "| 不是分隔行 | 12 |",
    "<img src=x onerror=alert(1)>",
  ]);
  assert.deepEqual(nodes.map((node) => node.tagName), ["p", "p", "p", "p"]);
  assert.equal(nodes[0].textContent, "上涨 4234 家 | 下跌 1152 家");
  assert.equal(nodes[3].textContent, "<img src=x onerror=alert(1)>");
  assert.equal(nodes[3].children.length, 0);
});

test("keeps malformed or incomplete tables visible as plain text", () => {
  const nodes = renderReportBlocks(document, ["| 行业 | 涨跌 |", "|---|---|", "| 电子 | +2% | 多余 |"]);
  assert.deepEqual(nodes.map((node) => node.tagName), ["p", "p", "p"]);
});

test("real A-share six-dimension and TOP10 sections become tables", () => {
  const report = reports.find((item) => item.id === "2026-09-18-evening");
  for (const title of ["六维观察", "七、行业板块 TOP10"]) {
    const section = report.sections.find((item) => item.title === title);
    const nodes = renderReportBlocks(document, section.paragraphs);
    const table = nodes.find((node) => node.tagName === "div")?.children[0];
    assert.equal(table?.tagName, "table", title);
    assert.equal(table.children[1].children.length, title === "六维观察" ? 6 : 10);
  }
});
