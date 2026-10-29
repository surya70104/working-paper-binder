// Markdown for working-paper fields (spec 7: "structured fields plus markdown").
// marked turns the text into HTML; DOMPurify removes anything that could run or load,
// so a paper can never inject script into a reviewer's browser. Nothing reaches the DOM
// without passing through sanitize().
import DOMPurify from "dompurify";
import { marked } from "marked";

marked.use({ gfm: true, breaks: true });

export function renderMarkdown(text: string): string {
  const html = marked.parse(text, { async: false });
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style", "form", "input", "button"],
    FORBID_ATTR: ["style"],
  });
}

export function Markdown({ text, className = "" }: { text: string; className?: string }) {
  if (!text.trim()) {
    return <p className={`text-slate-400 ${className}`}>—</p>;
  }
  return (
    <div
      className={`prose-sm max-w-none [&_a]:underline [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 [&_li]:ml-5 [&_ol]:list-decimal [&_p]:my-1 [&_ul]:list-disc ${className}`}
      // Safe: the HTML is DOMPurify output, see renderMarkdown.
      dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }}
    />
  );
}
