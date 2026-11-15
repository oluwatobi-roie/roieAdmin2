'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import CustomerProfileSummary from '@/components/CustomerProfileSummary';
import FinanceHistory from '@/components/FinanceHistory';
import ProfileRenewal from '@/components/ProfileRenewal';
import { expiryLabel } from '@/lib/finance';
import { useAuth } from '../hooks/useAuth';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import SearchDeviceCard, { SearchDevice as Device, SearchUserProfile as UserProfile } from '@/components/SearchDeviceCard';
import { FiSmartphone, FiUser, FiCpu, FiCalendar, FiMail, FiClock, FiCreditCard, FiChevronDown } from 'react-icons/fi';

type ProfilePanel = 'renewal' | 'finance' | 'devices';
const profileActions = [
  { id: 'renewal' as const, label: 'Extend Profile Expiry', Icon: FiClock },
  { id: 'finance' as const, label: 'Finance History', Icon: FiCreditCard },
  { id: 'devices' as const, label: 'View Devices', Icon: FiCpu },
];

interface SearchResponse {
  user?: UserProfile | null;
  devices?: Device[];
}

// ---------- Component ----------
export default function SearchPage() {
  const { auth_loading, authenticated } = useAuth();

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Device[]>([]);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [activePanel, setActivePanel] = useState<ProfilePanel | null>(null);
  const [visitedPanels, setVisitedPanels] = useState<ProfilePanel[]>([]);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [email, setEmail] = useState('');
  const [assignLoading, setAssignLoading] = useState(false);

  // ─── Search Handler ───
  const searchRequest = useRef<AbortController | null>(null);
  const loadSearch = useCallback(async (parameters: URLSearchParams) => {
    searchRequest.current?.abort();
    const controller = new AbortController();
    searchRequest.current = controller;
    setLoading(true);
    setFeedback('');
    setResults([]);
    setUserProfile(null);
    setActivePanel(null);
    setVisitedPanels([]);
    try {
      const res = await fetch(`/api/search?${parameters}`, { signal: controller.signal });
      const data: SearchResponse | Device[] = await res.json();
      if (controller.signal.aborted) return;
      if (!res.ok) throw new Error(res.status === 404 ? 'Customer or device not found.' : 'Unable to load this record. Please try again.');
      if (!data || (Array.isArray(data) && data.length === 0) || (!Array.isArray(data) && !data.user && !data.devices?.length)) {
        setFeedback('No results found.');
        return;
      }
      if (Array.isArray(data)) {
        setResults(data);
      } else {
        setResults(data.devices || []);
        setUserProfile(data.user || null);
      }
    } catch (err) {
      if (!controller.signal.aborted) setFeedback((err as Error).message || 'Error occurred while searching.');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    const userId = new URLSearchParams(window.location.search).get('user_id');
    if (userId !== null) void loadSearch(new URLSearchParams({ user_id: userId }));
    return () => searchRequest.current?.abort();
  }, [authenticated, loadSearch]);

  const handleSearch = () => {
    if (query.trim()) void loadSearch(new URLSearchParams({ term: query.trim() }));
  };

  const openAssignModal = (device: Device) => {
    setSelectedDevice(device);
    setIsModalOpen(true);
  };

  const handleAssign = async () => {
    if (!email || !selectedDevice?.device_id) return;
    setAssignLoading(true);

    try {
      const res = await fetch('/api/device/link_device', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, device_id: selectedDevice.device_id }),
      });
      const data = await res.json();
      if (res.ok) {
        alert('Device linked successfully!');
        setIsModalOpen(false);
        setEmail('');
      } else {
        alert(data.error || 'Failed to link device');
      }
    } catch (err) {
      console.error('Assign error:', err);
      alert('Unexpected error occurred');
    } finally {
      setAssignLoading(false);
    }
  };

  const profileId = userProfile?.id;
  const updateProfileExpiry = useCallback((expiry: string, disabled: boolean) => {
    setUserProfile(previous => previous && previous.id === profileId ? {
      ...previous, expiry, status: disabled ? 'Disabled' : new Date(expiry).getTime() <= Date.now() ? 'Expired' : 'Active',
    } : previous);
  }, [profileId]);

  const togglePanel = (panel: ProfilePanel) => {
    setVisitedPanels(previous => previous.includes(panel) ? previous : [...previous, panel]);
    setActivePanel(previous => previous === panel ? null : panel);
  };

  if (auth_loading) return <p className="text-center py-10">Loading your workspace...</p>;
  if (!authenticated) return null;

  return (
    <main className="min-h-screen bg-slate-50 px-3 py-6 text-slate-800 sm:px-6 sm:py-9 md:px-10">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-700">Customer workspace</p>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">Search Records</h1>
          <p className="text-sm leading-relaxed text-slate-500">Find a customer by email, or a vehicle by name, IMEI or phone.</p>
        </header>
        <form className="flex gap-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm sm:gap-3 sm:p-4" onSubmit={event => { event.preventDefault(); handleSearch(); }}>
          <label htmlFor="record-search" className="sr-only">Customer email or device details</label>
          <Input id="record-search" type="text" placeholder="e.g. GGE 173 XN or user@email.com" value={query} onChange={event => setQuery(event.target.value)} className="h-11 min-w-0 flex-1 border-slate-200 shadow-none" />
          <Button type="submit" disabled={loading} className="h-11 rounded-xl bg-blue-700 px-4 text-white hover:bg-blue-800">{loading ? 'Searching...' : 'Search'}</Button>
        </form>
        {feedback && <p role="alert" className="rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-800">{feedback}</p>}

        {userProfile && <section aria-label="Customer profile" className="space-y-5">
          <div className="min-w-0 rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="p-5 sm:p-6">
              <div className="flex items-start gap-3 sm:gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-700 sm:h-14 sm:w-14"><FiUser size={24} aria-hidden="true" /></div>
                <div className="min-w-0 flex-1">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">User Profile</h2>
                  <h3 className="mt-1 break-words text-xl font-semibold leading-snug text-slate-900 [overflow-wrap:anywhere] sm:text-2xl">{userProfile.name}</h3>
                  <span className={`mt-2 inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${userProfile.status === 'Active' ? 'bg-blue-50 text-blue-800' : 'bg-red-50 text-red-800'}`}>{userProfile.status}</span>
                </div>
              </div>
              <dl className="mt-6 grid min-w-0 gap-5 text-sm sm:grid-cols-2 lg:grid-cols-3">
                <div className="min-w-0"><dt className="flex items-center gap-2 text-xs font-medium text-slate-500"><FiMail aria-hidden="true" />Email</dt><dd className="mt-1.5 break-words font-medium [overflow-wrap:anywhere]">{userProfile.email || 'Not available'}</dd></div>
                <div className="min-w-0"><dt className="flex items-center gap-2 text-xs font-medium text-slate-500"><FiSmartphone aria-hidden="true" />Phone number</dt><dd className="mt-1.5 break-words font-medium [overflow-wrap:anywhere]">{userProfile.phone || 'Not available'}</dd></div>
                <div className="min-w-0"><dt className="flex items-center gap-2 text-xs font-medium text-slate-500"><FiCalendar aria-hidden="true" />Profile expiry</dt><dd className="mt-1.5 font-medium leading-relaxed">{expiryLabel(userProfile.expiry)}</dd></div>
              </dl>
            </div>
            {userProfile.id && <div className="px-5 pb-5 sm:px-6"><CustomerProfileSummary key={`summary-${userProfile.id}`} userId={userProfile.id} /></div>}
          </div>

          <div role="group" aria-label="Profile actions" className="grid gap-3 sm:grid-cols-3">
            {profileActions.map(({ id, label, Icon }) => <button key={id} id={`profile-action-${id}`} type="button" aria-label={label} aria-controls={`profile-panel-${id}`} aria-expanded={activePanel === id} onClick={() => togglePanel(id)} className={`flex min-h-16 min-w-0 items-center gap-3 rounded-xl border p-4 text-left text-sm font-semibold shadow-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 ${activePanel === id ? 'border-blue-700 bg-blue-700 text-white' : 'border-slate-200 bg-white text-blue-900 hover:border-blue-300 hover:bg-blue-50'}`}>
              <Icon className="h-5 w-5 shrink-0" aria-hidden="true" /><span className="min-w-0 flex-1">{label}</span><FiChevronDown className={`shrink-0 transition-transform ${activePanel === id ? 'rotate-180' : ''}`} aria-hidden="true" />
            </button>)}
          </div>

          <div id="profile-panel-renewal" hidden={activePanel !== 'renewal'} role="region" aria-labelledby="profile-action-renewal" className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">Extend profile expiry</h2>
            {visitedPanels.includes('renewal') && userProfile.id && <ProfileRenewal key={`renewal-${userProfile.id}`} userId={userProfile.id} onUpdated={updateProfileExpiry} />}
          </div>
          <div id="profile-panel-finance" hidden={activePanel !== 'finance'} role="region" aria-labelledby="profile-action-finance" className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">Finance history</h2>
            {visitedPanels.includes('finance') && userProfile.id && <FinanceHistory key={`finance-${userProfile.id}`} userId={userProfile.id} />}
          </div>
        </section>}

        {(userProfile || results.length > 0) && <section id="profile-panel-devices" hidden={!!userProfile && activePanel !== 'devices'} aria-label="Devices" className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold text-slate-900">Devices <span className="ml-1 text-sm font-normal text-slate-500">({results.length})</span></h2><p className="text-xs text-slate-500">Status, location and linked accounts</p></div>
          {!results.length && <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">No devices found for this account.</p>}
          <div className="grid min-w-0 items-start gap-4 lg:grid-cols-2">
            {results.map(device => <SearchDeviceCard key={device.device_id} device={device} onAssign={openAssignModal} />)}
          </div>
        </section>}
      </div>

      {isModalOpen && selectedDevice && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
        <div role="dialog" aria-modal="true" aria-labelledby="assign-device-title" className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-2xl bg-white p-5 shadow-xl sm:p-6">
          <h2 id="assign-device-title" className="text-lg font-semibold text-blue-950">Assign device</h2>
          <p className="mt-2 break-words text-sm text-slate-600 [overflow-wrap:anywhere]">{selectedDevice.device_name}</p>
          <label htmlFor="assign-email" className="mb-2 mt-5 block text-sm font-medium">User email</label>
          <Input id="assign-email" type="email" placeholder="Enter user email" className="h-11 w-full min-w-0 border-slate-200" value={email} onChange={event => setEmail(event.target.value)} />
          <div className="mt-5 flex flex-wrap justify-end gap-3">
            <Button onClick={() => setIsModalOpen(false)} variant="secondary">Cancel</Button>
            <Button onClick={handleAssign} disabled={assignLoading} className="bg-blue-700 text-white hover:bg-blue-800">{assignLoading ? 'Assigning...' : 'Assign'}</Button>
          </div>
        </div>
      </div>}
    </main>
  );
}
