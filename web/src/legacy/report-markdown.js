function textElement(document, tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  return element;
}

function pipeCells(line) {
  const text = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  if (!text.includes("|")) return null;
  const cells = [];
  let cell = "";
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === "\\" && text[index + 1] === "|") {
      cell += "|";
      index += 1;
    } else if (text[index] === "|") {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += text[index];
    }
  }
  cells.push(cell.trim());
  return cells;
}

function tableAt(lines, start) {
  const header = pipeCells(lines[start]);
  const alignment = pipeCells(lines[start + 1] ?? "");
  if (!header || !alignment || header.length !== alignment.length ||
      !alignment.every((cell) => /^:?-{3,}:?$/.test(cell))) return null;
  const rows = [];
  let end = start + 2;
  while (end < lines.length) {
    const cells = pipeCells(lines[end]);
    if (!cells) break;
    rows.push(cells);
    end += 1;
  }
  if (!rows.length || rows.some((row) => row.length !== header.length)) return null;
  return { header, alignment, rows, end };
}

function renderTable(document, tableData) {
  const wrapper = document.createElement("div");
  wrapper.className = "report-table-scroll";
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const body = document.createElement("tbody");
  const headRow = document.createElement("tr");
  tableData.header.forEach((value, index) => {
    const cell = textElement(document, "th", value);
    if (tableData.alignment[index].endsWith(":")) cell.className = "is-numeric";
    headRow.append(cell);
  });
  head.append(headRow);
  tableData.rows.forEach((values) => {
    const row = document.createElement("tr");
    values.forEach((value, index) => {
      const cell = textElement(document, "td", value);
      if (tableData.alignment[index].endsWith(":")) cell.className = "is-numeric";
      row.append(cell);
    });
    body.append(row);
  });
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

function listItem(line) {
  const unordered = /^[-*+]\s+(.+)$/.exec(line);
  if (unordered) return { kind: "ul", text: unordered[1] };
  const ordered = /^\d+[.)]\s+(.+)$/.exec(line);
  return ordered ? { kind: "ol", text: ordered[1] } : null;
}

function renderReportBlocks(document, lines) {
  const blocks = [];
  for (let index = 0; index < lines.length;) {
    const line = String(lines[index]).trim();
    if (!line) { index += 1; continue; }
    const table = tableAt(lines, index);
    if (table) {
      blocks.push(renderTable(document, table));
      index = table.end;
      continue;
    }
    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) {
      blocks.push(textElement(document, `h${Math.min(6, heading[1].length + 2)}`, heading[2]));
      index += 1;
      continue;
    }
    const item = listItem(line);
    if (item) {
      const list = document.createElement(item.kind);
      while (index < lines.length) {
        const next = listItem(String(lines[index]).trim());
        if (!next || next.kind !== item.kind) break;
        list.append(textElement(document, "li", next.text));
        index += 1;
      }
      blocks.push(list);
      continue;
    }
    blocks.push(textElement(document, "p", line));
    index += 1;
  }
  return blocks;
}

if (typeof module !== "undefined") module.exports = { renderReportBlocks };
if (typeof window !== "undefined") window.reportMarkdown = { renderReportBlocks };
