"use client";

import { useEffect, useState } from "react";
import type { UserProfile } from "@/lib/api";

/**
 * The name shown for a user: the editable display name, falling back to the
 * local part of the email so accounts created before the field existed still
 * render something sensible.
 */
export function displayNameOf(user: UserProfile | null | undefined): string {
  if (!user) return "";
  return user.display_name?.trim() || user.email.split("@")[0];
}

interface UserAvatarProps {
  /** Resolved image URL; falls back to the initial letter when missing/broken. */
  src?: string | null;
  name: string;
  /** Tailwind size classes for the circle. */
  className?: string;
  /** Font size for the initial-letter fallback. */
  textClassName?: string;
}

export default function UserAvatar({
  src,
  name,
  className = "h-8 w-8",
  textClassName = "text-sm",
}: UserAvatarProps) {
  const [broken, setBroken] = useState(false);

  // A new upload should get another chance to load even if the old one failed.
  useEffect(() => setBroken(false), [src]);

  if (src && !broken) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={name}
        className={`${className} shrink-0 rounded-full border border-border bg-bg-secondary object-cover`}
        onError={() => setBroken(true)}
      />
    );
  }

  return (
    <span
      aria-hidden="true"
      className={`${className} ${textClassName} inline-flex shrink-0 select-none items-center justify-center rounded-full bg-accent font-semibold uppercase text-accent-ink`}
    >
      {name.slice(0, 1) || "?"}
    </span>
  );
}
