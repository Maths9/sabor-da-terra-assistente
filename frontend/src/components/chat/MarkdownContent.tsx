import { Fragment, type ReactNode } from "react";

interface ListParseResult {
  node: ReactNode;
  nextIndex: number;
}

interface ListItemData {
  lines: string[];
  children: ReactNode[];
}

function isWordChar(ch: string | undefined): boolean {
  return Boolean(ch && /[A-Za-z0-9_\u00C0-\u024F]/.test(ch));
}

function isSafeUrl(rawUrl: string): boolean {
  try {
    const parsed = new URL(rawUrl);
    return parsed.protocol === "http:" || parsed.protocol === "https:" || parsed.protocol === "mailto:";
  } catch {
    return false;
  }
}

function countIndent(line: string): number {
  const expanded = line.replace(/\t/g, "  ");
  const m = expanded.match(/^(\s*)/);
  return m ? m[1].length : 0;
}

function parseListMarker(line: string): { indent: number; ordered: boolean; start: number; content: string } | null {
  const expanded = line.replace(/\t/g, "  ");
  const ul = expanded.match(/^(\s*)[-*+]\s+(.*)$/);
  if (ul) {
    return { indent: ul[1].length, ordered: false, start: 1, content: ul[2] };
  }
  const ol = expanded.match(/^(\s*)(\d+)[.)]\s+(.*)$/);
  if (ol) {
    return { indent: ol[1].length, ordered: true, start: Number(ol[2]), content: ol[3] };
  }
  return null;
}

function isTableSeparator(line: string): boolean {
  return /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(line) && line.includes("-");
}

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function isHorizontalRule(line: string): boolean {
  return /^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line);
}

function isBlockStarter(lines: string[], index: number): boolean {
  const line = lines[index];
  if (!line || !line.trim()) return true;
  if (/^\s*```/.test(line)) return true;
  if (isHorizontalRule(line)) return true;
  if (/^\s*#{1,6}\s+/.test(line)) return true;
  if (/^\s*>\s?/.test(line)) return true;
  if (parseListMarker(line)) return true;
  if (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) return true;
  return false;
}

/** Converte formatação inline de Markdown (negrito, itálico, código, links) em nós React seguros. */
function renderInline(text: string, keyPrefix = "in", depth = 0): ReactNode[] {
  if (!text) return [];
  if (depth > 4) return [text];

  const nodes: ReactNode[] = [];
  let plain = "";
  let i = 0;
  let seq = 0;

  const flush = () => {
    if (plain) {
      nodes.push(plain);
      plain = "";
    }
  };

  while (i < text.length) {
    if (text[i] === "\\" && i + 1 < text.length && /[*_`~[\]()#>-]/.test(text[i + 1])) {
      plain += text[i + 1];
      i += 2;
      continue;
    }

    if (text[i] === "`") {
      const end = text.indexOf("`", i + 1);
      if (end > i + 1) {
        flush();
        nodes.push(<code key={`${keyPrefix}-c-${seq++}`}>{text.slice(i + 1, end)}</code>);
        i = end + 1;
        continue;
      }
    }

    if (text[i] === "[") {
      const linkMatch = text.slice(i).match(/^\[([^\]]+)\]\(([^)\s]+)\)/);
      if (linkMatch) {
        const [, label, href] = linkMatch;
        if (isSafeUrl(href)) {
          flush();
          nodes.push(
            <a key={`${keyPrefix}-a-${seq++}`} href={href} target="_blank" rel="noopener noreferrer">
              {renderInline(label, `${keyPrefix}-l-${seq}`, depth + 1)}
            </a>
          );
          i += linkMatch[0].length;
          continue;
        }
      }
    }

    if (text.startsWith("***", i)) {
      const m = text.slice(i).match(/^\*\*\*([^\s*](?:[^*]*?[^\s*])?)\*\*\*/);
      if (m) {
        flush();
        nodes.push(
          <strong key={`${keyPrefix}-bi-${seq++}`}>
            <em>{renderInline(m[1], `${keyPrefix}-bi-${seq}`, depth + 1)}</em>
          </strong>
        );
        i += m[0].length;
        continue;
      }
    }

    if (text.startsWith("**", i)) {
      const m = text.slice(i).match(/^\*\*(\S(?:[\s\S]*?\S)?)\*\*/);
      if (m) {
        flush();
        nodes.push(
          <strong key={`${keyPrefix}-b-${seq++}`}>
            {renderInline(m[1], `${keyPrefix}-b-${seq}`, depth + 1)}
          </strong>
        );
        i += m[0].length;
        continue;
      }
    }

    if (text.startsWith("__", i) && !isWordChar(text[i - 1])) {
      const m = text.slice(i).match(/^__(\S(?:[\s\S]*?\S)?)__/);
      if (m && !isWordChar(text[i + m[0].length])) {
        flush();
        nodes.push(
          <strong key={`${keyPrefix}-bu-${seq++}`}>
            {renderInline(m[1], `${keyPrefix}-bu-${seq}`, depth + 1)}
          </strong>
        );
        i += m[0].length;
        continue;
      }
    }

    if (text.startsWith("~~", i)) {
      const m = text.slice(i).match(/^~~(\S(?:[\s\S]*?\S)?)~~/);
      if (m) {
        flush();
        nodes.push(
          <del key={`${keyPrefix}-s-${seq++}`}>
            {renderInline(m[1], `${keyPrefix}-s-${seq}`, depth + 1)}
          </del>
        );
        i += m[0].length;
        continue;
      }
    }

    if (text[i] === "*" && text[i + 1] !== "*") {
      const m = text.slice(i).match(/^\*([^\s*](?:[^*]*?[^\s*])?)\*/);
      if (m) {
        flush();
        nodes.push(
          <em key={`${keyPrefix}-em-${seq++}`}>
            {renderInline(m[1], `${keyPrefix}-em-${seq}`, depth + 1)}
          </em>
        );
        i += m[0].length;
        continue;
      }
    }

    if (text[i] === "_" && text[i + 1] !== "_" && !isWordChar(text[i - 1])) {
      const m = text.slice(i).match(/^_([^\s_](?:[^_]*?[^\s_])?)_/);
      if (m && !isWordChar(text[i + m[0].length])) {
        flush();
        nodes.push(
          <em key={`${keyPrefix}-emu-${seq++}`}>
            {renderInline(m[1], `${keyPrefix}-emu-${seq}`, depth + 1)}
          </em>
        );
        i += m[0].length;
        continue;
      }
    }

    plain += text[i];
    i += 1;
  }

  flush();
  return nodes;
}

function renderLinesWithBreaks(lines: string[], keyPrefix: string): ReactNode[] {
  return lines.map((line, idx) => (
    <Fragment key={`${keyPrefix}-ln-${idx}`}>
      {idx > 0 && <br />}
      {renderInline(line, `${keyPrefix}-ln-${idx}`)}
    </Fragment>
  ));
}

function findNextNonBlank(lines: string[], start: number): number {
  let idx = start;
  while (idx < lines.length && !lines[idx].trim()) {
    idx += 1;
  }
  return idx;
}

function parseList(lines: string[], start: number, keyPrefix: string): ListParseResult {
  const first = parseListMarker(lines[start])!;
  const baseIndent = first.indent;
  const ordered = first.ordered;
  const startNum = first.start;
  const items: ListItemData[] = [];
  let i = start;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      const nextIdx = findNextNonBlank(lines, i + 1);
      if (nextIdx >= lines.length) {
        i = nextIdx;
        break;
      }
      const nextMarker = parseListMarker(lines[nextIdx]);
      if (nextMarker && (nextMarker.indent > baseIndent || (nextMarker.indent === baseIndent && nextMarker.ordered === ordered))) {
        i = nextIdx;
        continue;
      }
      break;
    }

    const marker = parseListMarker(line);
    if (marker) {
      if (marker.indent < baseIndent) break;
      if (marker.indent > baseIndent) {
        const nested = parseList(lines, i, `${keyPrefix}-sub-${items.length}`);
        if (items.length === 0) {
          items.push({ lines: [], children: [nested.node] });
        } else {
          items[items.length - 1].children.push(nested.node);
        }
        i = nested.nextIndex;
        continue;
      }
      if (marker.ordered !== ordered) break;
      items.push({ lines: [marker.content], children: [] });
      i += 1;
      continue;
    }

    if (items.length > 0 && (countIndent(line) > baseIndent || !isBlockStarter(lines, i))) {
      items[items.length - 1].lines.push(line.trim());
      i += 1;
      continue;
    }
    break;
  }

  const Tag = ordered ? "ol" : "ul";
  const node = (
    <Tag key={keyPrefix} start={ordered && startNum !== 1 ? startNum : undefined}>
      {items.map((item, idx) => (
        <li key={`${keyPrefix}-li-${idx}`}>
          {item.lines.length > 0 && renderLinesWithBreaks(item.lines, `${keyPrefix}-li-${idx}`)}
          {item.children}
        </li>
      ))}
    </Tag>
  );

  return { node, nextIndex: i };
}

function renderHeading(level: number, text: string, key: string): ReactNode {
  const children = renderInline(text, key);
  switch (level) {
    case 1: return <h1 key={key}>{children}</h1>;
    case 2: return <h2 key={key}>{children}</h2>;
    case 3: return <h3 key={key}>{children}</h3>;
    case 4: return <h4 key={key}>{children}</h4>;
    case 5: return <h5 key={key}>{children}</h5>;
    default: return <h6 key={key}>{children}</h6>;
  }
}

function renderMarkdownBlocks(markdown: string, keyPrefix = "md"): ReactNode[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let seq = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (/^\s*```/.test(line)) {
      const codeLines: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length && /^\s*```/.test(lines[i])) i += 1;
      blocks.push(
        <pre key={`${keyPrefix}-pre-${seq++}`}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    if (isHorizontalRule(line)) {
      blocks.push(<hr key={`${keyPrefix}-hr-${seq++}`} />);
      i += 1;
      continue;
    }

    const heading = line.match(/^\s*(#{1,6})\s+(.+?)\s*#*$/);
    if (heading) {
      blocks.push(renderHeading(heading[1].length, heading[2], `${keyPrefix}-h-${seq++}`));
      i += 1;
      continue;
    }

    if (line.includes("|") && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      const headers = splitTableRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim() && lines[i].includes("|") && !isHorizontalRule(lines[i])) {
        rows.push(splitTableRow(lines[i]));
        i += 1;
      }
      const key = `${keyPrefix}-tbl-${seq++}`;
      blocks.push(
        <div key={key} className="md-table-wrap">
          <table>
            <thead>
              <tr>
                {headers.map((cell, ci) => (
                  <th key={`${key}-th-${ci}`}>{renderInline(cell, `${key}-th-${ci}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={`${key}-tr-${ri}`}>
                  {headers.map((_, ci) => (
                    <td key={`${key}-td-${ri}-${ci}`}>{renderInline(row[ci] ?? "", `${key}-td-${ri}-${ci}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      const key = `${keyPrefix}-bq-${seq++}`;
      blocks.push(<blockquote key={key}>{renderMarkdownBlocks(quoteLines.join("\n"), key)}</blockquote>);
      continue;
    }

    if (parseListMarker(line)) {
      const parsed = parseList(lines, i, `${keyPrefix}-list-${seq++}`);
      blocks.push(parsed.node);
      i = parsed.nextIndex;
      continue;
    }

    const paraLines: string[] = [];
    while (i < lines.length && !isBlockStarter(lines, i)) {
      paraLines.push(lines[i]);
      i += 1;
    }
    if (paraLines.length > 0) {
      const key = `${keyPrefix}-p-${seq++}`;
      blocks.push(<p key={key}>{renderLinesWithBreaks(paraLines, key)}</p>);
    } else {
      i += 1;
    }
  }

  return blocks;
}

/** Renderiza respostas do assistente em Markdown de forma segura sem HTML bruto. */
export default function MarkdownContent({ content }: { content: string }) {
  return <div className="md-content">{renderMarkdownBlocks(content)}</div>;
}
