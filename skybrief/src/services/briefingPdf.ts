import type { BriefingPack, FlightPlan } from '../types';

/** Dependency-free PDF export for the clearly labeled demo briefing. */
const WIDTH = 612;
const HEIGHT = 792;
const MARGIN = 46;
const LINE_HEIGHT = 14;
const CHARS_PER_LINE = 91;

// The built-in PDF Helvetica fonts are WinAnsi, not Unicode. Normalize uncommon
// characters to readable ASCII so PDFs open reliably even with no network.
function safe(value: unknown): string {
  return String(value ?? '')
    .replace(/\u2014|\u2013/g, '-')
    .replace(/\u2018|\u2019/g, "'")
    .replace(/\u201c|\u201d/g, '"')
    .replace(/\u00b0/g, ' degrees ')
    .replace(/\u00a7/g, 'Section ')
    .replace(/\u2022/g, '-')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^\x20-\x7e]/g, '?');
}
function escapePdf(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
}
function splitLines(input: string, max = CHARS_PER_LINE): string[] {
  const result: string[] = [];
  for (const paragraph of safe(input).split(/\r?\n/)) {
    const words = paragraph.split(/\s+/).filter(Boolean);
    if (!words.length) { result.push(''); continue; }
    let line = '';
    for (const word of words) {
      if (!line) {
        if (word.length <= max) line = word;
        else {
          for (let i = 0; i < word.length; i += max) result.push(word.slice(i, i + max));
        }
      } else if (line.length + word.length + 1 <= max) line += ` ${word}`;
      else {
        result.push(line);
        if (word.length <= max) line = word;
        else {
          for (let i = 0; i < word.length; i += max) result.push(word.slice(i, i + max));
          line = '';
        }
      }
    }
    if (line) result.push(line);
  }
  return result;
}

type PdfPage = { commands: string[]; y: number };
interface DemoBriefingPdf {
  briefing: BriefingPack;
  flightPlan: FlightPlan | null;
  generatedAt: string;
}

function buildPdfPages(item: DemoBriefingPdf): PdfPage[] {
  const pages: PdfPage[] = [];
  let page: PdfPage;
  const addPage = () => {
    page = { commands: [], y: HEIGHT - 55 };
    pages.push(page);
    // A standing warning on EVERY page, even if printed separately.
    page.commands.push('0.72 0.14 0.14 rg');
    //page.commands.push(`BT /F2 9 Tf ${MARGIN} ${HEIGHT - 33} Td (${escapePdf('DEMO PDF - NOT LIVE FAA AUTHORIZATION')}) Tj ET`);
    page.commands.push('0 0 0 rg');
  };
  addPage();
  function lines(text: string, bold = false, fontSize = 10, spaceAfter = 4) {
    const max = Math.max(32, Math.floor(CHARS_PER_LINE * (10 / fontSize)));
    for (const line of splitLines(text, max)) {
      if (page.y < 65) addPage();
      page.commands.push(`BT /${bold ? 'F2' : 'F1'} ${fontSize} Tf ${MARGIN} ${page.y} Td (${escapePdf(line)}) Tj ET`);
      page.y -= fontSize <= 10 ? LINE_HEIGHT : fontSize + 5;
    }
    page.y -= spaceAfter;
  }
  function section(title: string) { page.y -= 5; lines(title, true, 12, 7); }

  lines('SkyBrief - Flight Briefing', true, 17, 12);
  //lines('DEMO / MOCK DATA - NOT REAL FLIGHT CONDITIONS', true, 11, 8);
  lines(`Location: ${item.flightPlan?.location.displayName ?? item.briefing.locationLabel}`);
  if (item.flightPlan) {
    lines(`Coordinates: ${item.flightPlan.location.lat}, ${item.flightPlan.location.lng}`);
    lines(`Planned flight: ${item.flightPlan.date} ${item.flightPlan.time} (local as entered)`);
    lines(`Planned altitude: ${item.flightPlan.plannedAltitudeFt} ft AGL`);
  } else lines(`Planned flight: ${item.briefing.dateTimeLabel}`);
  lines(`PDF generated at: ${item.generatedAt}`);
  lines(`Briefing generated at: ${item.briefing.generatedAt}`);
  lines(`Original verdict (NOT revalidated): ${item.briefing.verdict.result.toUpperCase()}`, true);
  lines('Downloaded copies are static snapshots. Conditions and restrictions can change.', true);
  lines('Verify current FAA restrictions, authorization needs and weather before flying.', true);

  section('Briefing summary');
  lines(item.briefing.verdict.summary);
  if (item.briefing.verdict.factors.length) {
    section('Verdict factors');
    item.briefing.verdict.factors.forEach(x => lines(`- ${x}`));
  }
  section('Applicable rules and source references');
  item.briefing.findings.forEach((finding, i) => {
    lines(`${i + 1}. [${finding.status.toUpperCase()}] ${finding.title}${finding.mocked ? ' [MOCKED]' : ''}`, true);
    lines(finding.explanation);
    lines(`Source: ${finding.citation.source}`);
    lines(`URL: ${finding.citation.url || 'Not provided'}`, false, 9, 7);
  });
  section('Risk factors');
  item.briefing.riskFactors.forEach((factor) => {
    lines(`[${factor.severity.toUpperCase()}] ${factor.label}`, true);
    lines(factor.detail);
  });
  section('Suggested alternative (not verified)');
  lines(`${item.briefing.alternative.name} (${item.briefing.alternative.distance})`);
  lines(item.briefing.alternative.reason);
  lines(`Coordinates: ${item.briefing.alternative.coordinates.lat}, ${item.briefing.alternative.coordinates.lng}`);
  section('Privacy and limitations');
  lines('This demo report is a static PDF file. Conditions and restrictions can change.');
  lines('This report is educational and not official clearance or legal advice.');
  return pages;
}

/** Returns raw PDF bytes; no network calls or dependencies. */
export function createBriefingPdf(item: DemoBriefingPdf): Uint8Array {
  const pages = buildPdfPages(item);
  const objects: string[] = [];
  const add = (s: string) => { objects.push(s); return objects.length; };
  const catalogId = add('');
  const pagesId = add('');
  const regularId = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
  const boldId = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>');
  const pageIds: number[] = [];
  pages.forEach((page, index) => {
    page.commands.push(`BT /F1 8 Tf ${MARGIN} 32 Td (${escapePdf(`SkyBrief | Page ${index + 1} of ${pages.length} | Demo snapshot`)}) Tj ET`);
    const stream = page.commands.join('\n') + '\n';
    const streamId = add(`<< /Length ${stream.length} >>\nstream\n${stream}endstream`);
    pageIds.push(add(`<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${WIDTH} ${HEIGHT}] /Resources << /Font << /F1 ${regularId} 0 R /F2 ${boldId} 0 R >> >> /Contents ${streamId} 0 R >>`));
  });
  objects[catalogId - 1] = `<< /Type /Catalog /Pages ${pagesId} 0 R >>`;
  objects[pagesId - 1] = `<< /Type /Pages /Kids [${pageIds.map(id => `${id} 0 R`).join(' ')}] /Count ${pageIds.length} >>`;
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((object, i) => {
    offsets.push(pdf.length);
    pdf += `${i + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefPosition = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  offsets.slice(1).forEach(pos => { pdf += `${String(pos).padStart(10, '0')} 00000 n \n`; });
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root ${catalogId} 0 R >>\nstartxref\n${xrefPosition}\n%%EOF\n`;
  return new TextEncoder().encode(pdf);
}

/** Trigger an actual demo .pdf file download directly in the user's browser. */
export function downloadDemoBriefingPdf(briefing: BriefingPack, flightPlan: FlightPlan | null): void {
  const generatedAt = new Date().toISOString();
  const bytes = createBriefingPdf({ briefing, flightPlan, generatedAt });
  const blob = new Blob([new Uint8Array(bytes)], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  const date = flightPlan?.date || generatedAt.slice(0, 10);
  anchor.href = url;
  anchor.download = `SkyBrief-demo-${date}.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30000);
}
