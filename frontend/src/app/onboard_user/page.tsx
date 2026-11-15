'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { FiUser, FiMail, FiPhone } from 'react-icons/fi';

export default function OnboardUserPage() {
  // ---------- AUTH PROTECTION ----------
  const { auth_loading, authenticated } = useAuth();

  // ---------- FORM STATE ----------
  const [createdEmail, setCreatedEmail] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [loadingForm, setLoadingForm] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // ---------- HANDLE ONBOARD ----------
  const handleOnboard = async () => {
    if (!name || !email || !phone) {
      setFeedback({ type: 'error', message: 'All fields are required.' });
      return;
    }

    setLoadingForm(true);
    setFeedback(null);

    try {
      const res = await fetch('/api/user/onboarduser', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, phone }),
        credentials: 'include',
      });

      const data = await res.json();

      if (res.ok) {
        setFeedback({ type: 'success', message: 'User onboarded successfully!' });
        setCreatedEmail(email);
        setName('');
        setEmail('');
        setPhone('');
      } else {
        setFeedback({ type: 'error', message: data.error || 'Failed to onboard user' });
      }
    } catch (err) {
      console.error('Onboard error:', err);
      setFeedback({ type: 'error', message: 'Unexpected error occurred.' });
    } finally {
      setLoadingForm(false);
    }
  };

  // ---------- CONDITIONAL RENDER ----------
  if (auth_loading) return <p className="text-center py-10">Checking You have access... please wait</p>;
  if (!authenticated) return null;

  // ---------- RENDER ----------
  return (
    <main className="min-h-screen bg-gray-50 px-4 py-10 sm:px-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-blue-900">👤 Onboard New User</h1>
        <p className="text-slate-500 text-sm sm:text-base">
          Enter user details to create a new account
        </p>

        {/* Feedback */}
        {feedback && (
          <p
            className={`text-center py-2 px-4 rounded-md ${
              feedback.type === 'success'
                ? 'bg-green-100 text-green-700'
                : 'bg-red-100 text-red-700'
            }`}
          >
            {feedback.message}
          </p>
        )}

        {createdEmail && <Link className="inline-block rounded-lg bg-blue-800 px-5 py-3 text-sm font-medium text-white" href={`/finance?new=1&customer_email=${encodeURIComponent(createdEmail)}`}>Create invoice for this customer</Link>}
        <Link className="block text-sm text-blue-800 underline" href="/finance?new=1">Back to finance</Link>
        {/* Form Card */}
        <Card className="shadow-sm border border-slate-200 rounded-2xl bg-white">
          <CardContent className="p-6 space-y-4">
            <div className="flex items-center gap-2 text-gray-700">
              <FiUser className="text-blue-900" />
              <Input
                type="text"
                placeholder="Full Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="flex-1"
              />
            </div>

            <div className="flex items-center gap-2 text-gray-700">
              <FiMail className="text-blue-900" />
              <Input
                type="email"
                placeholder="Email Address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="flex-1"
              />
            </div>

            <div className="flex items-center gap-2 text-gray-700">
              <FiPhone className="text-blue-900" />
              <Input
                type="tel"
                placeholder="Phone Number"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="flex-1"
              />
            </div>

            <Button
              onClick={handleOnboard}
              disabled={loadingForm}
              className="w-full bg-blue-800 hover:bg-blue-900 text-white mt-2"
            >
              {loadingForm ? 'Onboarding...' : 'Onboard User'}
            </Button>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
