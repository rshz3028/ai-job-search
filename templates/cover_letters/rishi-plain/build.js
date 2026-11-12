// Generic renderer for the candidate's plain Calibri cover letter (from build_cl_valeo_ann.js / build_cl_nxp_ics.js).
// Usage: node build.js <content.json>   -> writes <content>.docx next to the JSON.
const fs = require("fs");
const path = require("path");
const { Document, Packer, Paragraph, TextRun, AlignmentType } = require(path.join(__dirname, "..", "..", "node_modules", "docx"));

const NAVY = "1B2A4A";
const jsonPath = path.resolve(process.argv[2]);
const c = JSON.parse(fs.readFileSync(jsonPath, "utf8"));

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.after ?? 200 },
    alignment: opts.align ?? AlignmentType.LEFT,
    children: [new TextRun({ text, size: 21, font: "Calibri", bold: opts.bold ?? false })],
  });
}

const children = [
  new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: c.name, bold: true, size: 22, font: "Calibri", color: NAVY })] }),
  p(c.contactLine, { after: 400 }),
];
if (c.date) children.push(p(c.date, { after: 240 }));
children.push(p(c.subject, { bold: true, after: 300 }));
children.push(p(c.salutation, { after: 240 }));
for (const para of c.paragraphs) children.push(p(para, { after: 240 }));
children.push(p(c.closing, { after: 200 }));
children.push(p(c.name, { bold: true }));

const doc = new Document({
  creator: c.name,
  title: c.name + " - Cover Letter",
  sections: [{ properties: { page: { margin: { top: 1000, bottom: 1000, left: 1200, right: 1200 } } }, children }],
});
const out = jsonPath.replace(/\.json$/i, ".docx");
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(out, buf); console.log("Wrote " + out); });
