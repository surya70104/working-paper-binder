import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { Markdown, renderMarkdown } from "../src/markdown";

test("ordinary markdown renders as structure", () => {
  const html = renderMarkdown(
    "Cash is **fairly stated**.\n\n- 4 accounts confirmed\n- 0 exceptions\n\nSee [SA 505](https://example.test/sa505).",
  );
  expect(html).toContain("<strong>fairly stated</strong>");
  expect(html).toContain("<ul>");
  expect(html).toContain("<li>4 accounts confirmed</li>");
  expect(html).toContain('<a href="https://example.test/sa505">SA 505</a>');
});

test("tables and line breaks are supported", () => {
  const html = renderMarkdown("| Account | Balance |\n|---|---|\n| HDFC | 1,00,000 |\n\nline one\nline two");
  expect(html).toContain("<table>");
  expect(html).toContain("<td>HDFC</td>");
  expect(html).toContain("line one<br>line two");
});

test.each([
  ["<script>alert(1)</script>", "<script"],
  ['<img src=x onerror="alert(1)">', "onerror"],
  ['<a href="javascript:alert(1)">click</a>', "javascript:"],
  ["<iframe src=\"https://evil.test\"></iframe>", "<iframe"],
  ['<div onclick="steal()">x</div>', "onclick"],
  ['<p style="position:fixed">overlay</p>', "style="],
  ['<form action="https://evil.test"><input name="pw"></form>', "<form"],
  ["<svg><script>alert(1)</script></svg>", "<script"],
])("hostile content is neutralised: %s", (input, forbidden) => {
  const html = renderMarkdown(`Conclusion ${input} end`);
  expect(html).not.toContain(forbidden);
  expect(html).toContain("Conclusion");
  expect(html).toContain("end");
});

test("the Markdown component renders sanitised HTML and an em dash for nothing", () => {
  render(<Markdown text="A *note* with <script>alert(1)</script> inside" />);
  expect(screen.getByText("note").tagName).toBe("EM");
  expect(document.querySelector("script")).toBeNull();
  render(<Markdown text="   " />);
  expect(screen.getByText("—")).toBeInTheDocument();
});
