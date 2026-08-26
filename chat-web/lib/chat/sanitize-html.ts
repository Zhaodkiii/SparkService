/**
 * Minimal white-list HTML sanitizer for server-provided `html` blocks.
 *
 * Only a small set of structural/formatting tags and safe attributes survive;
 * scripts, styles, forms, frames and dangerous URLs are stripped. This is a
 * security boundary because the source is an untrusted server payload rendered
 * into the DOM via React's `dangerouslySetInnerHTML`.
 */

const ALLOWED_TAGS = new Set([
  "P", "BR", "B", "STRONG", "I", "EM", "U", "S", "A", "UL", "OL", "LI",
  "H1", "H2", "H3", "H4", "H5", "H6", "BLOCKQUOTE", "CODE", "PRE", "SPAN",
  "DIV", "TABLE", "THEAD", "TBODY", "TR", "TH", "TD", "IMG", "HR",
]);
const ALLOWED_ATTRS = new Set(["href", "src", "alt", "title", "colspan", "rowspan", "start", "rel"]);

function safeUrl(value: string, allowMailto: boolean): boolean {
  return /^(https?:\/\/)/i.test(value) || (allowMailto && /^(mailto:|#)/i.test(value));
}

export function sanitizeHtml(raw: string): string {
  if (typeof raw !== "string" || !raw.trim()) return "";
  if (typeof DOMParser === "undefined") return "";
  const doc = new DOMParser().parseFromString(raw, "text/html");
  const body = doc.body;

  const walk = (node: Element): void => {
    for (const child of Array.from(node.children)) {
      if (!ALLOWED_TAGS.has(child.tagName)) {
        const text = child.textContent ?? "";
        const replacement = child.ownerDocument.createTextNode(text);
        child.replaceWith(replacement);
        continue;
      }
      for (const attr of Array.from(child.attributes)) {
        const name = attr.name.toLowerCase();
        if (!ALLOWED_ATTRS.has(name)) {
          child.removeAttribute(attr.name);
          continue;
        }
        if (name === "href" && !safeUrl(attr.value, true)) child.removeAttribute(attr.name);
        if (name === "src" && !safeUrl(attr.value, false)) child.removeAttribute(attr.name);
        if (name === "target") child.removeAttribute(attr.name); // never allow target control
      }
      if (child.tagName === "A") child.setAttribute("rel", "noreferrer noopener");
      if (child.tagName === "IMG") { child.removeAttribute("onerror"); child.setAttribute("loading", "lazy"); }
      walk(child);
    }
  };
  walk(body);
  return body.innerHTML;
}