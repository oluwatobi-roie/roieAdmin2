'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import Image from 'next/image';
import { useState } from 'react';
import { FiHome, FiSearch, FiUserPlus, FiPlus, FiCreditCard, FiLogOut } from 'react-icons/fi';

const links = [
  { href: '/', label: 'Home', shortLabel: 'Home', Icon: FiHome },
  { href: '/search', label: 'Search', shortLabel: 'Search', Icon: FiSearch },
  { href: '/onboard_user', label: 'Onboard Users', shortLabel: 'Users', Icon: FiUserPlus },
  { href: '/add-device', label: 'Add Device', shortLabel: 'Devices', Icon: FiPlus },
  { href: '/finance', label: 'Finance', shortLabel: 'Finance', Icon: FiCreditCard },
];

export default function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);
  const handleLogout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      const response = await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
      if (!response.ok) throw new Error('Could not finish signing out. Please retry.');
      router.replace('/login'); router.refresh();
    } catch { window.alert('Could not finish signing out. Please retry.'); }
    finally { setLoggingOut(false); }
  };
  return <>
    <header className="app-header sticky top-0 z-40 h-16 border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-full max-w-7xl items-center px-4 sm:px-6">
        <Link href="/" aria-label="RoieTrackers home"><Image src="/logo.svg" alt="RoieTrackers" width={130} height={70} /></Link>
      </div>
    </header>
    <nav aria-label="Main navigation" className="app-navigation">
      {links.map(({ href, label, shortLabel, Icon }) => <Link key={href} href={href} aria-label={label} aria-current={pathname === href ? 'page' : undefined} className="app-nav-item">
        <Icon aria-hidden="true" /><span className="lg:hidden">{shortLabel}</span><span className="hidden lg:block">{label}</span>
      </Link>)}
      <button type="button" className="app-nav-item" aria-label="Logout" disabled={loggingOut} onClick={() => void handleLogout()}><FiLogOut aria-hidden="true" /><span>{loggingOut ? 'Exiting' : 'Logout'}</span></button>
    </nav>
  </>;
}
