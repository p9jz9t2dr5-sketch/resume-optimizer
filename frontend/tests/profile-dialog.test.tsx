import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProfileDialog from "@/components/user/ProfileDialog";
import type { UserProfile } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { useToastStore } from "@/stores/toastStore";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
}));

const user: UserProfile = {
  id: "u1",
  email: "zhangsan@example.com",
  display_name: "演示",
  avatar_url: "./uploads/avatar_1.png",
  is_premium: false,
  created_at: "2026-01-01T00:00:00Z",
};

function toastMessages(): string[] {
  return useToastStore.getState().toasts.map((t) => t.message);
}

function setup(overrides: Partial<UserProfile> = {}) {
  const updateProfile = vi.fn().mockResolvedValue(undefined);
  const uploadAvatar = vi.fn().mockResolvedValue(undefined);
  const removeAvatar = vi.fn().mockResolvedValue(undefined);
  const deleteAccount = vi.fn().mockResolvedValue(undefined);

  useAuthStore.setState({
    user: { ...user, ...overrides },
    isAuthenticated: true,
    isLoading: false,
    updateProfile,
    uploadAvatar,
    removeAvatar,
    deleteAccount,
  });
  useToastStore.setState({ toasts: [] });

  const onClose = vi.fn();
  render(<ProfileDialog onClose={onClose} />);
  return { updateProfile, uploadAvatar, removeAvatar, deleteAccount, onClose };
}

function fileInput(): HTMLInputElement {
  const input = document.querySelector('input[type="file"]');
  if (!input) throw new Error("file input not rendered");
  return input as HTMLInputElement;
}

describe("ProfileDialog", () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] });
  });

  it("prefills the nickname and shows the login email", () => {
    setup();

    expect(screen.getByLabelText("昵称")).toHaveValue("演示");
    expect(screen.getByText(/zhangsan@example\.com/)).toBeInTheDocument();
  });

  it("falls back to the email prefix when no nickname is stored", () => {
    setup({ display_name: null });

    expect(screen.getByLabelText("昵称")).toHaveValue("zhangsan");
  });

  it("saves the trimmed nickname", async () => {
    const { updateProfile } = setup();

    fireEvent.change(screen.getByLabelText("昵称"), { target: { value: "  李四  " } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith("李四"));
  });

  it("refuses an empty nickname", async () => {
    const { updateProfile } = setup();

    fireEvent.change(screen.getByLabelText("昵称"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(toastMessages()).toContain("昵称不能为空"));
    expect(updateProfile).not.toHaveBeenCalled();
  });

  it("enforces the 8 character limit", async () => {
    const { updateProfile } = setup();

    // The input carries maxLength for typing; fireEvent bypasses it, which is
    // exactly the case the guard has to catch.
    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "一二三四五六七八九" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(toastMessages()).toContain("昵称最多 8 个字"));
    expect(updateProfile).not.toHaveBeenCalled();
  });

  it("uploads a chosen image before saving the nickname", async () => {
    const { updateProfile, uploadAvatar } = setup();
    const png = new File(["fake-bytes"], "me.png", { type: "image/png" });

    fireEvent.change(fileInput(), { target: { files: [png] } });
    expect(screen.getByAltText("演示")).toBeInTheDocument(); // local preview

    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(uploadAvatar).toHaveBeenCalledWith(png));
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith("演示"));
  });

  it("rejects non-image files without uploading", async () => {
    const { uploadAvatar } = setup();

    fireEvent.change(fileInput(), {
      target: { files: [new File(["x"], "notes.txt", { type: "text/plain" })] },
    });

    await waitFor(() => expect(toastMessages()).toContain("仅支持 PNG / JPG / WebP 格式的图片"));
    expect(uploadAvatar).not.toHaveBeenCalled();
  });

  it("removes the current avatar", async () => {
    const { removeAvatar } = setup();

    fireEvent.click(screen.getByRole("button", { name: /移除/ }));

    await waitFor(() => expect(removeAvatar).toHaveBeenCalled());
  });

  it("hides the remove button when there is no avatar yet", () => {
    setup({ avatar_url: null });

    expect(screen.queryByRole("button", { name: /移除/ })).not.toBeInTheDocument();
  });

  it("requires a second click before deleting the account", async () => {
    const { deleteAccount } = setup();

    fireEvent.click(screen.getByRole("button", { name: "删除我的账号" }));

    // Nothing happens on the first click: it only reveals the confirmation.
    expect(deleteAccount).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /确认永久删除/ })).toBeInTheDocument();
  });

  it("deletes the account and redirects home after confirmation", async () => {
    const { deleteAccount, onClose } = setup();

    fireEvent.click(screen.getByRole("button", { name: "删除我的账号" }));
    fireEvent.click(screen.getByRole("button", { name: /确认永久删除/ }));

    await waitFor(() => expect(deleteAccount).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(push).toHaveBeenCalledWith("/");
  });
});
