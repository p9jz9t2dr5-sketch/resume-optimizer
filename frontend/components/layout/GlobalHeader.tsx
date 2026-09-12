"use client";

import { usePathname } from "next/navigation";
import Navbar from "./Navbar";

// The landing page renders its own LandingHeader, so the shared Navbar is
// suppressed on the exact home route ("/"). All other public routes
// (login / register / companies) keep the global Navbar unchanged.
export default function GlobalHeader() {
  const pathname = usePathname();
  if (pathname === "/") return null;
  return <Navbar />;
}
