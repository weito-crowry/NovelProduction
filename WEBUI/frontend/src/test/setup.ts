import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

const NativeRequest = globalThis.Request;
globalThis.Request = class TestRequest extends NativeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(input, init ? { ...init, signal: undefined } : undefined);
  }
};

if (typeof document.elementFromPoint !== "function") {
  Object.defineProperty(document, "elementFromPoint", {
    configurable: true,
    value: () => null,
  });
}

if (!("getClientRects" in Text.prototype)) {
  Object.defineProperty(Text.prototype, "getClientRects", {
    configurable: true,
    value: () => [],
  });
}

if (!("getClientRects" in Element.prototype)) {
  Object.defineProperty(Element.prototype, "getClientRects", {
    configurable: true,
    value: () => [],
  });
}

if (!("getClientRects" in Range.prototype)) {
  Object.defineProperty(Range.prototype, "getClientRects", {
    configurable: true,
    value: () => [],
  });
}

if (!("getBoundingClientRect" in Range.prototype)) {
  Object.defineProperty(Range.prototype, "getBoundingClientRect", {
    configurable: true,
    value: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
  });
}
