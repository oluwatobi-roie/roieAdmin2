'use client';

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import Image from "next/image";

export default function Header() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "include",
      });
    } catch (err) {
      console.error("Logout failed:", err);
    } finally {
      router.push("/login"); // always redirect to login
    }
  };

  const links = [
    { href: "/", label: "Home" },
    { href: "/search", label: "Search" },
    { href: "/onboard_user", label: "Onboard Users" },
    { href: "/add-device", label: "Add Device" },
    { href: "/#", label: "Finance" },
  ];

  return (
    <header className="bg-[#428fda] text-white shadow sticky top-0 z-50">
      <div className="max-w-7xl mx-auto flex items-center justify-between px-6 py-3">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2">
          <Image src="/logo.svg" alt="Roie Logo" width={80} height={200} />
        </Link>

        {/* Navigation */}
        <nav className="flex gap-6 items-center">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`hover:text-gray-200 transition-colors ${
                pathname === link.href ? "font-semibold underline" : ""
              }`}
            >
              {link.label}
            </Link>
          ))}

          {/* Logout Button */}
          <button
            onClick={handleLogout}
            className="hover:text-gray-200 transition-colors"
          >
            Logout
          </button>
        </nav>
      </div>
    </header>
  );
}
