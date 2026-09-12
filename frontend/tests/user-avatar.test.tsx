import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { UserProfile } from "@/lib/api";
import UserAvatar, { displayNameOf } from "@/components/user/UserAvatar";

const baseUser: UserProfile = {
  id: "u1",
  email: "zhangsan@example.com",
  display_name: null,
  avatar_url: null,
  is_premium: false,
  created_at: "2026-01-01T00:00:00Z",
};

describe("displayNameOf", () => {
  it("prefers the editable display name", () => {
    expect(displayNameOf({ ...baseUser, display_name: "  张三  " })).toBe("张三");
  });

  it("falls back to the email local part for accounts created before the field existed", () => {
    expect(displayNameOf(baseUser)).toBe("zhangsan");
  });

  it("handles a missing user", () => {
    expect(displayNameOf(null)).toBe("");
  });
});

describe("UserAvatar", () => {
  it("shows the first character when there is no avatar", () => {
    render(<UserAvatar name="张三" />);
    expect(screen.getByText("张")).toBeInTheDocument();
  });

  it("renders the image when a src is provided", () => {
    render(<UserAvatar src="http://example.com/a.png" name="张三" />);
    expect(screen.getByRole("img")).toHaveAttribute("src", "http://example.com/a.png");
    expect(screen.getByRole("img")).toHaveAttribute("alt", "张三");
  });

  it("falls back to the initial when the image fails to load", () => {
    render(<UserAvatar src="http://example.com/broken.png" name="Bob" />);

    fireEvent.error(screen.getByRole("img"));

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
  });

  it("retries when the src changes after a failure", () => {
    const { rerender } = render(<UserAvatar src="http://example.com/broken.png" name="Bob" />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();

    rerender(<UserAvatar src="http://example.com/fresh.png" name="Bob" />);

    expect(screen.getByRole("img")).toHaveAttribute("src", "http://example.com/fresh.png");
  });
});
