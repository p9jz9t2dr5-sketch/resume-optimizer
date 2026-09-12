import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/stores/authStore";
import RegisterPage from "@/app/(auth)/register/page";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
}));

function fill(password: string, confirm: string, email = "new@example.com") {
  render(<RegisterPage />);
  fireEvent.change(screen.getByPlaceholderText("your@email.com"), { target: { value: email } });
  fireEvent.change(screen.getByPlaceholderText("至少 8 位"), { target: { value: password } });
  fireEvent.change(screen.getByPlaceholderText("再次输入密码"), { target: { value: confirm } });
  fireEvent.submit(document.querySelector("form") as HTMLFormElement);
}

describe("RegisterPage", () => {
  beforeEach(() => {
    push.mockClear();
    useAuthStore.setState({ register: vi.fn().mockResolvedValue(undefined) });
  });

  it("rejects mismatched passwords before hitting the API", () => {
    const register = vi.fn();
    useAuthStore.setState({ register });

    fill("Passw0rd!123", "Passw0rd!124");

    expect(screen.getByText("两次输入的密码不一致")).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });

  it("enforces the same 8 character minimum the API enforces", () => {
    const register = vi.fn();
    useAuthStore.setState({ register });

    fill("short7c", "short7c"); // 7 characters

    expect(screen.getByText("密码长度至少 8 位")).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });

  it("registers and redirects to the dashboard", async () => {
    const register = vi.fn().mockResolvedValue(undefined);
    useAuthStore.setState({ register });

    fill("Passw0rd!123", "Passw0rd!123", "fresh@example.com");

    await waitFor(() => expect(register).toHaveBeenCalledWith("fresh@example.com", "Passw0rd!123"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/dashboard"));
  });
});
