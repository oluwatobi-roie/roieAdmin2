'use client';

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import Image from "next/image";
import { useState } from "react";
import { FiHome, FiSearch, FiUserPlus, FiPlus, FiMenu, FiX, FiCreditCard, FiLogOut } from "react-icons/fi";

export default function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "include",
      });
    } catch (err) {
      console.error("Logout failed:", err);
    } finally {
      router.push("/login");
    }
  };

  const links = [
    { href: "/", label: "Home", icon: <FiHome /> },
    { href: "/search", label: "Search", icon: <FiSearch /> },
    { href: "/onboard_user", label: "Onboard Users", icon: <FiUserPlus /> },
    { href: "/add-device", label: "Add Device", icon: <FiPlus /> },
    { href: "/finance", label: "Finance", icon: <FiCreditCard /> },
  ];

  return (
    <header className="bg-white text-slate-700 border-b border-slate-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto flex items-center justify-between px-6 py-3">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2">
          <Image src="/logo.svg" alt="Roie Logo" width={130} height={70} />
        </Link>

        {/* Hamburger for small screens */}
        <button
          className="lg:hidden text-slate-700 text-2xl"
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          {menuOpen ? <FiX /> : <FiMenu />}
        </button>

        {/* Navigation */}
        <nav className={`flex-col lg:flex-row lg:flex gap-4 items-start lg:items-center absolute lg:static top-full left-0 w-full lg:w-auto bg-white lg:bg-transparent transition-all overflow-hidden lg:overflow-visible ${menuOpen ? 'max-h-96 py-4 lg:py-0' : 'max-h-0 lg:max-h-full'}`}>
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-1 px-6 lg:px-0 py-2 lg:py-0 hover:text-blue-800 transition-colors ${
                pathname === link.href ? "font-semibold text-blue-800 underline underline-offset-8" : ""
              }`}
              onClick={() => setMenuOpen(false)}
            >
              {link.icon} {link.label}
            </Link>
          ))}

          {/* Logout Button */}
          <button
            onClick={handleLogout}
            className="flex items-center gap-1 px-6 lg:px-0 py-2 lg:py-0 hover:text-blue-800 transition-colors"
          >
            <FiLogOut /> Logout
          </button>
        </nav>
      </div>
    </header>
  );
}
