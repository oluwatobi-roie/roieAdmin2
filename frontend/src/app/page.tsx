"use client";
import Link from 'next/link';
import { FiSearch, FiPlus, FiUserPlus, FiCreditCard, FiArrowUpRight } from 'react-icons/fi';
import { useAuth } from './hooks/useAuth';

const shortcuts = [
  { href: '/search', title: 'Search', label: 'Search customers and vehicles', Icon: FiSearch },
  { href: '/onboard_user', title: 'New customer', label: 'Onboard a customer', Icon: FiUserPlus },
  { href: '/add-device', title: 'Add device', label: 'Add a device', Icon: FiPlus },
  { href: '/finance', title: 'Finance', label: 'Open finance', Icon: FiCreditCard },
];
export default function Home() {
  const { auth_loading, authenticated } = useAuth();
  if (auth_loading) return <p className="p-8 text-center text-slate-500">Loading workspace...</p>;
  if (!authenticated) return null;
  return <main className="roie-page home-page">
    <div className="home-workspace">
      <h1 className="roie-page-title">Your workspace</h1>
      <section aria-label="Quick actions" className="home-grid">
        {shortcuts.map(({ href, title, label, Icon }) => <Link key={href} href={href} aria-label={label} className="home-shortcut roie-card">
          <span className="home-shortcut-icon"><Icon aria-hidden="true" /></span>
          <h2>{title}</h2><FiArrowUpRight className="home-shortcut-arrow" aria-hidden="true" />
        </Link>)}
      </section>
    </div>
  </main>;
}
