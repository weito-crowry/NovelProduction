import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { Editor } from "@tiptap/core";
import { describe, expect, test } from "vitest";

import { phaseEExtensions } from "./phaseEExtensions";

const fixtureHtml = readFileSync(
  resolve(process.cwd(), "../../tests/fixtures/phase_e_tiptap_roundtrip.html"),
  "utf8",
);

describe("Phase E TipTap boundary feasibility", () => {
  test("shared fixture survives semantic TipTap serialization", () => {
    const editor = new Editor({
      extensions: phaseEExtensions,
      content: fixtureHtml,
    });

    expect(semanticHtml(editor.getHTML())).toEqual(semanticHtml(fixtureHtml));
    editor.destroy();
  });
});

function semanticHtml(html: string): string[] {
  const document = new DOMParser().parseFromString(`<main>${html}</main>`, "text/html");
  const root = document.querySelector("main");
  if (!root) {
    throw new Error("semantic fixture root is missing");
  }
  return Array.from(root.childNodes)
    .filter((node) => !(node.nodeType === Node.TEXT_NODE && !node.textContent?.trim()))
    .map((node) => semanticNode(node));
}

function semanticNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) {
    return `text:${node.textContent ?? ""}`;
  }
  if (!(node instanceof Element)) {
    throw new Error("unexpected non-element semantic node");
  }
  const tag = node.tagName.toLowerCase();
  if (tag === "ruby") {
    const reading = node.querySelector(":scope > rt")?.textContent ?? "";
    const base = Array.from(node.childNodes)
      .filter((child) => !(child instanceof Element && child.tagName.toLowerCase() === "rt"))
      .map((child) => child.textContent ?? "")
      .join("");
    return `ruby(${base}|${reading})`;
  }
  const attributes = [
    "id",
    "data-np-type",
    "data-np-scene-id",
    "data-np-speaker-id",
    "data-ann-emotions",
    "data-emphasis",
  ]
    .map((name) => `${name}=${node.getAttribute(name) ?? ""}`)
    .filter((entry) => !entry.endsWith("="))
    .join(",");
  const children = Array.from(node.childNodes)
    .filter((child) => !(child.nodeType === Node.TEXT_NODE && !child.textContent))
    .map((child) => semanticNode(child))
    .join("|");
  return `${tag}[${attributes}](${children})`;
}
