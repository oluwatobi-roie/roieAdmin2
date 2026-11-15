"use client";
import { usePathname } from "next/navigation";
import Header from "./Header";

export default function ClientHeaderWrapper() {
  const pathname = usePathname();
  const hideHeaderOn = ["/login"]; // add more if needed

  if (hideHeaderOn.includes(pathname)) return null;
  return <Header />;
}
