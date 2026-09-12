import { afterEach, describe, expect, it, vi } from "vitest";

import { API_BASE, mediaUrl, resumeApi } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("mediaUrl", () => {
  it("prefixes the API base and strips the leading './'", () => {
    expect(mediaUrl("./uploads/avatar_1.png")).toBe(`${API_BASE}/uploads/avatar_1.png`);
  });

  it("normalises Windows-style separators", () => {
    expect(mediaUrl(".\\uploads\\avatar_1.png")).toBe(`${API_BASE}/uploads/avatar_1.png`);
  });

  it("returns null for missing values so callers can fall back to initials", () => {
    expect(mediaUrl(null)).toBeNull();
    expect(mediaUrl(undefined)).toBeNull();
    expect(mediaUrl("")).toBeNull();
  });
});

describe("getErrorMessage", () => {
  it("prefers the thrown Error message", () => {
    expect(getErrorMessage(new Error("昵称不能为空"), "兜底文案")).toBe("昵称不能为空");
  });

  it("falls back for non-Error throws", () => {
    expect(getErrorMessage("boom", "兜底文案")).toBe("兜底文案");
    expect(getErrorMessage(undefined, "兜底文案")).toBe("兜底文案");
  });
});

describe("API error surfacing", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("surfaces FastAPI's `detail` field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "昵称最多 8 个字" }, 422))
    );

    await expect(resumeApi.list()).rejects.toThrow("昵称最多 8 个字");
  });

  it("falls back to the status code when the body has no detail", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));

    await expect(resumeApi.list()).rejects.toThrow("HTTP 500");
  });
});
