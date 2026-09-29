import { marked } from 'marked';
import sanitizeHtml from 'sanitize-html';

marked.setOptions({ gfm: true, breaks: false });

function compactSourceLines(markdown: string): string {
  return markdown.replace(/^(\s*-\s*来源：)(https:\/\/[^\n]+)$/gm, (line, prefix, sources) => {
    const urls: string[] = sources.split(/,\s+/);
    if (!urls.every((url: string) => /^https:\/\/\S+$/.test(url))) return line;
    return prefix + urls.map((url: string, index: number) => {
      const label = urls.length === 1 ? '来源' : `来源${index + 1}`;
      return `[${label}](${url.replace(/\(/g, '%28').replace(/\)/g, '%29')})`;
    }).join('、');
  });
}

export function renderMarkdown(markdown: string, { compactSources = false }: { compactSources?: boolean } = {}): string {
  const parsed = marked.parse(compactSources ? compactSourceLines(markdown) : markdown, { async: false });
  return sanitizeHtml(parsed, {
    allowedTags: [
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'hr', 'blockquote',
      'ul', 'ol', 'li', 'strong', 'em', 'code', 'pre', 'a',
      'table', 'thead', 'tbody', 'tr', 'th', 'td', 'del',
    ],
    allowedAttributes: { a: ['href', 'title', 'rel', 'target'], th: ['align'], td: ['align'] },
    allowedSchemes: ['http', 'https', 'mailto'],
    allowProtocolRelative: false,
    transformTags: {
      a: (_tag, attributes) => ({ tagName: 'a', attribs: {
        ...attributes,
        ...(attributes.href?.startsWith('http') ? { target: '_blank', rel: 'noopener noreferrer' } : {}),
      } }),
    },
  });
}
