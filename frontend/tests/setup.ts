import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Vitest only auto-cleans when `globals` is enabled; the suite keeps explicit
// imports, so unmount rendered trees here.
afterEach(() => {
  cleanup();
});

// jsdom implements neither of these, and the avatar preview needs them.
URL.createObjectURL = vi.fn(() => "blob:preview");
URL.revokeObjectURL = vi.fn();
