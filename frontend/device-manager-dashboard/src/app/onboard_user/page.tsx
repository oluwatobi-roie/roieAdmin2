'use client';

import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { FiUser, FiMail, FiPhone } from 'react-icons/fi';
import Image from 'next/image';

export default function OnboardUserPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const handleOnboard = async () => {
    if (!name || !email || !phone) {
      setFeedback({ type: 'error', message: 'All fields are required.' });
      return;
    }

    setLoading(true);
    setFeedback(null);

    try {
      const res = await fetch('/api/user/onboarduser', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, phone }),
      });

      const data = await res.json();

      if (res.ok) {
        setFeedback({
          type: 'success',
          message: `User onboarded successfully!}`,
        });
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
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-10 sm:px-8">
      <div className="max-w-4xl mx-auto space-y-6">
          <h1 className="text-2xl sm:text-3xl font-bold text-[#414095]">
            👤 Onboard New User
          </h1>
          <p className="text-[#428fda] text-sm sm:text-base">
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

        {/* Form Card */}
        <Card className="shadow-lg border border-[#428fda] rounded-xl bg-gradient-to-r from-[#e2e4f7] to-[#d6ebfa]">
          <CardContent className="p-6 space-y-4">
            <div className="flex items-center gap-2 text-gray-700">
              <FiUser className="text-[#414095]" />
              <Input
                type="text"
                placeholder="Full Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="flex-1"
              />
            </div>

            <div className="flex items-center gap-2 text-gray-700">
              <FiMail className="text-[#414095]" />
              <Input
                type="email"
                placeholder="Email Address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="flex-1"
              />
            </div>

            <div className="flex items-center gap-2 text-gray-700">
              <FiPhone className="text-[#414095]" />
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
              disabled={loading}
              className="w-full bg-[#428fda] hover:bg-[#414095] text-white mt-2"
            >
              {loading ? 'Onboarding...' : 'Onboard User'}
            </Button>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
