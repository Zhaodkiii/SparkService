import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
});

export function renderConversationMarkdown(source: string): string {
  const rendered = md.render(source || '');
  return DOMPurify.sanitize(rendered, {
    USE_PROFILES: { html: true },
  });
}

export function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
