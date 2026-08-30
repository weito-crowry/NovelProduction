import { Mark, Node } from "@tiptap/core";
import Bold from "@tiptap/extension-bold";
import Blockquote from "@tiptap/extension-blockquote";
import Document from "@tiptap/extension-document";
import HardBreak from "@tiptap/extension-hard-break";
import Heading from "@tiptap/extension-heading";
import HorizontalRule from "@tiptap/extension-horizontal-rule";
import Italic from "@tiptap/extension-italic";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";

const phaseEBlockAttributes = {
  id: explicitHtmlAttribute("id"),
  "data-np-type": explicitHtmlAttribute("data-np-type"),
  "data-np-scene-id": explicitHtmlAttribute("data-np-scene-id"),
  "data-np-speaker-id": explicitHtmlAttribute("data-np-speaker-id"),
  "data-ann-emotions": explicitHtmlAttribute("data-ann-emotions"),
  "data-np-remove-annotations": explicitHtmlAttribute("data-np-remove-annotations"),
};

export const PhaseEParagraph = Paragraph.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      ...phaseEBlockAttributes,
    };
  },
});

export const PhaseEBlockquote = Blockquote.extend({
  content: "inline*",

  addAttributes() {
    return {
      ...this.parent?.(),
      ...phaseEBlockAttributes,
    };
  },
});

export const PhaseEHeading = Heading.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      ...phaseEBlockAttributes,
    };
  },
}).configure({ levels: [1, 2, 3] });

export const PhaseEHorizontalRule = HorizontalRule.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      ...phaseEBlockAttributes,
    };
  },
});

export const PhaseEItalic = Italic.extend({
  parseHTML() {
    return [{ tag: 'em:not([data-emphasis="dot"])' }];
  },
});

export const PhaseEEmphasisDot = Mark.create({
  name: "phaseEEmphasisDot",

  parseHTML() {
    return [{ tag: 'em[data-emphasis="dot"]' }];
  },

  renderHTML() {
    return ["em", { "data-emphasis": "dot" }, 0];
  },
});

export const PhaseERuby = Node.create({
  name: "phaseERuby",
  group: "inline",
  inline: true,
  atom: true,

  addAttributes() {
    return {
      base: {
        default: "",
        parseHTML: (element: HTMLElement) => rubyBase(element),
      },
      reading: {
        default: "",
        parseHTML: (element: HTMLElement) =>
          element.querySelector(":scope > rt")?.textContent ?? "",
      },
    };
  },

  parseHTML() {
    return [{ tag: "ruby" }];
  },

  renderHTML({ node }) {
    return [
      "ruby",
      {},
      node.attrs.base,
      ["rt", {}, node.attrs.reading],
    ];
  },
});

export const phaseEExtensions = [
  Document,
  Text,
  PhaseEParagraph,
  PhaseEBlockquote,
  PhaseEHeading,
  PhaseEHorizontalRule,
  HardBreak,
  Bold,
  PhaseEItalic,
  PhaseEEmphasisDot,
  PhaseERuby,
];

function rubyBase(element: HTMLElement): string {
  return Array.from(element.childNodes)
    .filter(
      (child) =>
        !(
          child.nodeType === 1 &&
          (child as HTMLElement).tagName.toLowerCase() === "rt"
        ),
    )
    .map((child) => child.textContent ?? "")
    .join("");
}

function explicitHtmlAttribute(name: string) {
  return {
    default: null,
    keepOnSplit: false,
    parseHTML: (element: HTMLElement) => element.getAttribute(name),
    renderHTML: (attributes: Record<string, unknown>) => {
      const value = attributes[name];
      return value === null || value === undefined ? {} : { [name]: String(value) };
    },
  };
}
