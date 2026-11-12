// Generic renderer for the 1-page two-column sidebar CV (Calibri, blue sidebar, photo).
// Usage: node build.js <content.json>   -> writes <content>.docx next to the JSON.
// Layout copied from the candidate's original build_valeo_ann.js / build_nxp_ics.js.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, VerticalAlign, AlignmentType, ExternalHyperlink
} = require(path.join(__dirname, "..", "..", "node_modules", "docx"));

const NAVY = "1B4F72";
const SIDEBAR_BG = "2F5D8A";
const SBTEXT = "FFFFFF";
const DARKTEXT = "222222";
const GRAY = "555555";

const PAGE_W = 11906, PAGE_H = 16838;
const SIDEBAR_W = 3500;
const MAIN_W = PAGE_W - SIDEBAR_W;

const jsonPath = path.resolve(process.argv[2]);
const c = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
const photoPath = path.resolve(path.dirname(jsonPath), c.photo);
const photo = fs.readFileSync(photoPath);

function noBorder() {
  const n = { style: BorderStyle.NONE, size: 0, color: SIDEBAR_BG };
  return { top: n, bottom: n, left: n, right: n };
}
function sbHeading(text, first = false) {
  return new Paragraph({
    spacing: { before: first ? 0 : 220, after: 90 },
    children: [new TextRun({ text: text.toUpperCase(), bold: true, color: SBTEXT, size: 18, font: "Calibri" })],
  });
}
function sbBullet(text) {
  return new Paragraph({
    spacing: { after: 55, line: 264 },
    indent: { left: 170, hanging: 170 },
    children: [
      new TextRun({ text: "● ", color: SBTEXT, size: 17, font: "Calibri" }),
      new TextRun({ text, color: SBTEXT, size: 17, font: "Calibri" }),
    ],
  });
}
function sbPlain(text) {
  return new Paragraph({ spacing: { after: 45 }, children: [new TextRun({ text, color: SBTEXT, size: 17, font: "Calibri" })] });
}
function sbLink(text, url) {
  return new Paragraph({
    spacing: { after: 45 },
    children: [new ExternalHyperlink({ link: url, children: [new TextRun({ text, color: SBTEXT, size: 17, font: "Calibri" })] })],
  });
}
function mainHeading(text) {
  return new Paragraph({
    spacing: { before: 150, after: 80 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 3 } },
    children: [new TextRun({ text: text.toUpperCase(), bold: true, color: NAVY, size: 23, font: "Calibri" })],
  });
}
function entryHeader(title, dates) {
  return new Paragraph({
    spacing: { before: 80, after: 20 },
    tabStops: [{ type: "right", position: MAIN_W - 300 }],
    children: [
      new TextRun({ text: title, bold: true, color: DARKTEXT, size: 21, font: "Calibri" }),
      new TextRun({ text: "\t" + (dates || ""), italics: true, color: GRAY, size: 19, font: "Calibri" }),
    ],
  });
}
function subLine(text) {
  return new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text, italics: true, color: GRAY, size: 19, font: "Calibri" })] });
}
function bullet(text) {
  return new Paragraph({
    spacing: { after: 70, line: 280 },
    indent: { left: 220, hanging: 160 },
    children: [
      new TextRun({ text: "● ", color: DARKTEXT, size: 20, font: "Calibri" }),
      new TextRun({ text, color: DARKTEXT, size: 20, font: "Calibri" }),
    ],
  });
}
function bodyText(text) {
  return new Paragraph({ spacing: { after: 50, line: 280 }, children: [new TextRun({ text, color: DARKTEXT, size: 20, font: "Calibri" })] });
}
function techUsed(label, text) {
  return new Paragraph({ spacing: { after: 130 }, children: [new TextRun({ text: label + text, italics: true, color: GRAY, size: 18, font: "Calibri" })] });
}

// ---- sidebar ----
const ct = c.contact;
const sidebarChildren = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [new ImageRun({ data: photo, transformation: { width: 132, height: 132 }, type: "jpg" })],
  }),
  sbHeading(c.labels?.contact || "Contact", true),
  sbPlain(ct.phone),
  sbPlain(ct.email),
  sbPlain(ct.location),
  sbLink(ct.linkedin.text, ct.linkedin.url),
  sbLink(ct.github.text, ct.github.url),
];
for (const blk of c.sidebar) {
  sidebarChildren.push(sbHeading(blk.heading));
  for (const b of blk.bullets || []) sidebarChildren.push(sbBullet(b));
  for (const l of blk.lines || []) sidebarChildren.push(sbPlain(l));
}

// ---- main column ----
const mainChildren = [
  new Paragraph({ spacing: { after: 30 }, children: [new TextRun({ text: c.name.toUpperCase(), bold: true, size: 44, color: NAVY, font: "Calibri" })] }),
  new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: c.headline.toUpperCase(), bold: true, size: 19, color: NAVY, font: "Calibri" })] }),
];
const techLabel = c.labels?.techUsed || "Technologies used: ";
for (const sec of c.sections) {
  mainChildren.push(mainHeading(sec.heading));
  if (sec.text) mainChildren.push(bodyText(sec.text));
  for (const e of sec.entries || []) {
    mainChildren.push(entryHeader(e.title, e.dates));
    if (e.sub) mainChildren.push(subLine(e.sub));
    if (e.text) mainChildren.push(bodyText(e.text));
    for (const b of e.bullets || []) mainChildren.push(bullet(b));
    if (e.tech) mainChildren.push(techUsed(techLabel, e.tech));
  }
}

const table = new Table({
  width: { size: PAGE_W, type: WidthType.DXA },
  columnWidths: [SIDEBAR_W, MAIN_W],
  rows: [new TableRow({
    cantSplit: true,
    // Fill the whole page height so the blue sidebar runs to the bottom edge.
    height: { value: PAGE_H - 600, rule: "exact" },
    children: [
      new TableCell({
        width: { size: SIDEBAR_W, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: SIDEBAR_BG },
        margins: { top: 480, bottom: 480, left: 240, right: 240 },
        verticalAlign: VerticalAlign.TOP,
        borders: noBorder(),
        children: sidebarChildren,
      }),
      new TableCell({
        width: { size: MAIN_W, type: WidthType.DXA },
        margins: { top: 300, bottom: 150, left: 280, right: 240 },
        verticalAlign: VerticalAlign.TOP,
        borders: noBorder(),
        children: mainChildren,
      }),
    ],
  })],
});

const doc = new Document({
  creator: c.name,
  title: c.name + " - CV",
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: PAGE_H }, margin: { top: 0, bottom: 0, left: 0, right: 0, header: 0, footer: 0 } } },
    // Word always appends a paragraph after a table; keep it 1pt so it cannot spill to page 2.
    children: [table, new Paragraph({ run: { size: 2 }, spacing: { before: 0, after: 0, line: 20, lineRule: "exact" }, children: [new TextRun({ text: "", size: 2 })] })],
  }],
});

const out = jsonPath.replace(/\.json$/i, ".docx");
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(out, buf);
  console.log("Wrote " + out);
});
