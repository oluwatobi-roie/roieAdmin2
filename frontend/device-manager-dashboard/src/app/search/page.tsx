'use client';

import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { FiSmartphone, FiHash, FiInfo, FiMapPin, FiUser, FiCpu, FiCheckCircle, FiAlertTriangle, FiCalendar, FiMail } from 'react-icons/fi';
import Image from 'next/image';

export default function SearchPage() {
  // ---------- AUTH PROTECTION ----------
  const {auth_loading, authenticated } = useAuth();

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [userProfile, setUserProfile] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState('');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<any | null>(null);
  const [email, setEmail] = useState('');
  const [assignLoading, setAssignLoading] = useState(false);

  // ─── Search Handler ───
  const handleSearch = async () => {
    if (!query) return;
    setLoading(true);
    setFeedback('');
    setResults([]);
    setUserProfile(null);

    try {
      const res = await fetch(`/api/search?term=${query}`);
      const data = await res.json();

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
      console.error('Search error:', err);
      setFeedback('Error occurred while searching.');
    } finally {
      setLoading(false);
    }
  };

  const openAssignModal = (device: any) => {
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

  const handleUnlinkDevice = async (userId: string, deviceId: string) => {
    try {
      const res = await fetch('/api/device/unlink', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, device_id: deviceId }),
      });
      const data = await res.json();
      if (res.ok) {
        alert('User unlinked successfully!');
      } else {
        alert(data.error || 'Failed to unlink user');
      }
    } catch (err) {
      console.error('Unlink error:', err);
      alert('Unexpected error occurred');
    }
  };

  const getStatusStyles = (status: string) => {
    switch (status) {
      case 'NOC Passed Online':
        return 'text-green-600 font-semibold';
      case 'NOC Failed Online':
        return 'text-red-600 font-semibold';
      case 'Device is Offline':
        return 'text-gray-500 font-semibold';
      case 'Likely Online, but not updating frequently':
        return 'text-yellow-600 font-semibold';
      case 'Unknown':
      default:
        return 'text-indigo-600 font-semibold';
    }
  };

  const getRecommendationStyles = (recommendation: string) => {
    if (!recommendation || recommendation === 'None') return 'bg-green-100 text-green-700';
    if (recommendation.toLowerCase().includes('recharge')) return 'bg-red-100 text-red-700';
    if (recommendation.toLowerCase().includes('monitor')) return 'bg-yellow-100 text-yellow-800';
    if (recommendation.toLowerCase().includes('maintenance') || recommendation.toLowerCase().includes('check')) return 'bg-blue-100 text-blue-800';
    return 'bg-gray-100 text-gray-800';
  };

    // ---------- CONDITIONAL RENDER ----------
  if (auth_loading) return <p className="text-center py-10">Checking You have access... please wait</p>;
  if (!authenticated) return null;

  // ---------- RENDER ----------
  return (
    <main className="min-h-screen bg-gray-50 px-4 py-8 sm:px-6 md:px-12">
      <div className="max-w-5xl mx-auto space-y-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-[#414095]">
            👤Search Records
          </h1>
          <p className="text-[#428fda] text-sm sm:text-base">
            Search devices or users by name, IMEI, or email
          </p>

        {/* Search Input */}
        <div className="flex gap-3 justify-center flex-wrap">
          <Input
            type="text"
            placeholder="e.g. GGE 173 XN or user@email.com"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 max-w-md"
          />
          <Button
            onClick={handleSearch}
            disabled={loading}
            className="bg-[#414095] hover:bg-[#428fda] text-white"
          >
            {loading ? 'Searching...' : 'Search'}
          </Button>
        </div>

        {/* Feedback if no result */}
        {feedback && <p className="text-center text-red-600 mt-4">{feedback}</p>}

{/* User Profile */}
{userProfile && (
  <section className="mt-6">
    <h2 className="text-xl font-semibold text-[#414095] mb-2 flex items-center gap-2">
      <FiUser className="text-[#428fda]" /> User Profile
    </h2>
    <Card className="shadow-lg border border-[#428fda] hover:shadow-2xl transition-shadow bg-[#e8f0fb] rounded-xl">
      <CardContent className="p-4 space-y-2 text-gray-800">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold flex items-center gap-2">
            <FiUser /> {userProfile.name}
          </h3>
          <span className={`px-2 py-1 rounded-full text-xs font-semibold ${userProfile.status === 'Active' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
            {userProfile.status}
          </span>
        </div>

        <p className="flex items-center gap-2 text-gray-700">
          <FiMail /> {userProfile.email}
        </p>
        <p className="flex items-center gap-2 text-gray-700">
          <FiSmartphone /> {userProfile.phone}
        </p>
        <p className="flex items-center gap-2 text-gray-700">
          <FiCalendar /> Expiry: {new Date(userProfile.expiry).toLocaleString()}
        </p>
      </CardContent>
    </Card>
  </section>
)}




        {/* Devices List */}
{results.length > 0 && (
  <section className="mt-6 space-y-4">
    <h2 className="text-xl font-semibold text-[#414095] mb-2 flex items-center gap-2">
      <FiSmartphone className="text-[#428fda]" /> Devices
    </h2>
    {results.map((device: any, idx) => (
      <Card
        key={idx}
        className="shadow-lg border border-[#428fda] hover:shadow-2xl transition-shadow bg-gradient-to-r from-[#e2e4f7] to-[#d6ebfa] rounded-xl relative"
      >
        <CardContent className="p-4 space-y-2 text-gray-800">
          {/* Device header with status badge */}
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-lg font-bold flex items-center gap-2">
              <FiCpu /> {device.device_name}
            </h3>
            {device.online_status?.status && (
              <span className={`px-2 py-1 rounded-full text-xs font-semibold ${getStatusStyles(device.online_status.status)}`}>
                {device.online_status.status}
              </span>
            )}
          </div>

          {/* Device details */}
          <div className="flex flex-col gap-1 text-gray-600 text-sm">
            <p className="flex items-center gap-2 text-gray-400"><FiHash /> IMEI: {device.imei}</p>
            <p className="flex items-center gap-2 text-gray-400"><FiInfo /> Model: {device.model}</p>
            <p className="flex items-center gap-2"><FiSmartphone /> Phone: {device.phone}</p>
            <p className="flex items-center gap-2"><FiMapPin /> Address: {device.position_address}</p>
            {device.online_status?.recommendation && (
              <p className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${getRecommendationStyles(device.online_status.recommendation)}`}>
                <FiAlertTriangle className="inline mr-1" />
                {device.online_status.recommendation}
              </p>
            )}
          </div>

          {/* Attached users */}
          {device.user_profiles && (
            <div className="mt-3">
              <h4 className="text-sm font-semibold text-[#414095] mb-1">👥 Attached Users</h4>
              <div className="space-y-2">
                {device.user_profiles.map((user: any, i: number) => (
                  <div key={i} className="flex justify-between items-center bg-[#f0f4ff] p-2 rounded-md shadow-sm hover:shadow-md transition-shadow">
                    <div className="text-gray-800 text-sm">
                      <p className="font-medium">{user.name}</p>
                      <p className="text-gray-600">{user.email}</p>
                      <p className="text-gray-500">
                        Status: <span className="font-semibold">{user.status}</span> | Expiry: {new Date(user.expiry).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Assign button */}
          <div className="mt-3">
            <Button
              onClick={() => openAssignModal(device)}
              className="bg-[#428fda] hover:bg-[#414095] text-white"
            >
              Assign to a User
            </Button>
          </div>
        </CardContent>
      </Card>
    ))}
  </section>
)}

      </div>

      {/* Assign Modal */}
      {isModalOpen && selectedDevice && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 z-50">
          <div className="bg-white p-6 rounded-xl shadow-2xl w-80 sm:w-96">
            <h2 className="text-lg sm:text-xl font-bold mb-3 text-[#414095]">
              Assign Device: {selectedDevice.device_name}
            </h2>
            <Input
              type="email"
              placeholder="Enter user email"
              className="w-full mb-4 border-[#428fda] focus:ring-[#414095]"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <div className="flex justify-end gap-3">
              <Button onClick={() => setIsModalOpen(false)} variant="secondary">
                Cancel
              </Button>
              <Button
                onClick={handleAssign}
                disabled={assignLoading}
                className="bg-[#428fda] hover:bg-[#414095] text-white"
              >
                {assignLoading ? 'Assigning...' : 'Assign'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
