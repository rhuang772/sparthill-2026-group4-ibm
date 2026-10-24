import type { CheckResponse, FlightPlan } from '../types';

const WIDTH = 612;
const HEIGHT = 792;
const MARGIN = 46;
const LINE_HEIGHT = 14;
const CHARS_PER_LINE = 91;

export interface BriefingPdfData {
  response: CheckResponse;
  flightPlan: FlightPlan;
  generatedAt: string;
}

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
    if (!words.length) {
      result.push('');
      continue;
    }
    let line = '';
    for (const word of words) {
      if (!line) {
        if (word.length <= max) line = word;
        else {
          for (let i = 0; i < word.length; i += max) result.push(word.slice(i, i + max));
        }
      } else if (line.length + word.length + 1 <= max) {
        line += ` ${word}`;
      } else {
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

function buildPdfPages(data: BriefingPdfData): PdfPage[] {
  const pages: PdfPage[] = [];
  let page: PdfPage;
  const addPage = () => {
    page = { commands: [], y: HEIGHT - 55 };
    pages.push(page);
    page.commands.push('0.72 0.14 0.14 rg');
    page.commands.push(
      `BT /F2 9 Tf ${MARGIN} ${HEIGHT - 33} Td (${escapePdf('SAVED COPY - NOT LIVE FAA AUTHORIZATION')}) Tj ET`,
    );
    page.commands.push('0 0 0 rg');
  };
  addPage();

  function lines(text: string, bold = false, fontSize = 10, spaceAfter = 4) {
    const max = Math.max(32, Math.floor(CHARS_PER_LINE * (10 / fontSize)));
    for (const line of splitLines(text, max)) {
      if (page.y < 65) addPage();
      page.commands.push(
        `BT /${bold ? 'F2' : 'F1'} ${fontSize} Tf ${MARGIN} ${page.y} Td (${escapePdf(line)}) Tj ET`,
      );
      page.y -= fontSize <= 10 ? LINE_HEIGHT : fontSize + 5;
    }
    page.y -= spaceAfter;
  }

  lines('SkyBrief - Flight Briefing', true, 17, 12);
  lines(data.response.mock_data ? 'DEMO / MOCK DATA - VERIFY ALL INFORMATION' : 'Advisory briefing - verify current information', true, 11, 8);
  lines(`Location: ${data.flightPlan.location.displayName}`);
  lines(`Coordinates: ${data.flightPlan.location.lat}, ${data.flightPlan.location.lng}`);
  lines(`Planned flight: ${data.flightPlan.date} ${data.flightPlan.time} (local as entered)`);
  lines(`Planned altitude: ${data.flightPlan.plannedAltitudeFt} ft AGL`);
  lines(`Search radius: ${data.flightPlan.radiusMeters} m`);
  lines(`Generated at: ${data.generatedAt}`);
  lines('Downloaded copies are static snapshots. Conditions and restrictions can change.', true);
  lines('Verify current FAA restrictions, authorization needs, and weather before flying.', true);
  lines('');

  for (const line of data.response.answer_markdown.split(/\r?\n/)) {
    const heading = /^#{1,3}\s/.test(line);
    const text = line
      .replace(/^#{1,6}\s*/, '')
      .replace(/^\s*[-*]\s/, '- ')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/`([^`]+)`/g, '$1');
    lines(text, heading, heading ? 12 : 10, heading ? 5 : 3);
  }

  for (const [source, checkedAt] of Object.entries(data.response.data_freshness)) {
    lines(`${source} checked at: ${checkedAt}`, false, 9);
  }
  if (data.response.sources_failed.length) {
    lines(`Sources that failed: ${data.response.sources_failed.join(', ')}`, true);
  }

  return pages;
}

export function createBriefingPdf(data: BriefingPdfData): Uint8Array {
  const pages = buildPdfPages(data);
  const objects: string[] = [];
  const add = (value: string) => {
    objects.push(value);
    return objects.length;
  };
  const catalogId = add('');
  const pagesId = add('');
  const regularId = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
  const boldId = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>');
  const pageIds: number[] = [];

  pages.forEach((pdfPage, index) => {
    pdfPage.commands.push(
      `BT /F1 8 Tf ${MARGIN} 32 Td (${escapePdf(`SkyBrief | Page ${index + 1} of ${pages.length} | Saved snapshot`)}) Tj ET`,
    );
    const stream = `${pdfPage.commands.join('\n')}\n`;
    const streamId = add(`<< /Length ${stream.length} >>\nstream\n${stream}endstream`);
    pageIds.push(
      add(
        `<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${WIDTH} ${HEIGHT}] /Resources << /Font << /F1 ${regularId} 0 R /F2 ${boldId} 0 R >> >> /Contents ${streamId} 0 R >>`,
      ),
    );
  });

  objects[catalogId - 1] = `<< /Type /Catalog /Pages ${pagesId} 0 R >>`;
  objects[pagesId - 1] = `<< /Type /Pages /Kids [${pageIds.map(id => `${id} 0 R`).join(' ')}] /Count ${pageIds.length} >>`;
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefPosition = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  offsets.slice(1).forEach(position => {
    pdf += `${String(position).padStart(10, '0')} 00000 n \n`;
  });
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root ${catalogId} 0 R >>\nstartxref\n${xrefPosition}\n%%EOF\n`;
  return new TextEncoder().encode(pdf);
}

export function downloadBriefingPdf(data: BriefingPdfData): void {
  const bytes = createBriefingPdf(data);
  const blob = new Blob([new Uint8Array(bytes)], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  const date = data.flightPlan.date || new Date(data.generatedAt).toISOString().slice(0, 10);
  anchor.href = url;
  anchor.download = `SkyBrief-${date}.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30000);
}
