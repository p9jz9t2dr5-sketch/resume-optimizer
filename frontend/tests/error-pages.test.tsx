import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ErrorBoundary from "@/app/error";
import NotFound from "@/app/not-found";

describe("NotFound", () => {
  it("explains the situation and offers a way back", () => {
    render(<NotFound />);

    expect(screen.getByRole("heading", { name: "页面不存在" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "回到首页" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "进入控制面板" })).toHaveAttribute("href", "/dashboard");
  });
});

describe("ErrorBoundary", () => {
  it("lets the user retry the failed render", () => {
    const reset = vi.fn();
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(<ErrorBoundary error={new Error("boom")} reset={reset} />);
    fireEvent.click(screen.getByRole("button", { name: /重试/ }));

    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "回到首页" })).toHaveAttribute("href", "/");
  });
});
