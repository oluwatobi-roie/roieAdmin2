"use client";

import Link from 'next/link';
import { useAuth } from './hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import Image from 'next/image';

export default function Home() {

    // ---------- AUTH PROTECTION ----------
const {auth_loading, authenticated } = useAuth();

      // ---------- CONDITIONAL RENDER ----------
  if (auth_loading) return <p className="text-center py-10">Checking session...</p>;
  if (!authenticated) return null;

  // ---------- RENDER ----------
  return (
    <main className="min-h-screen bg-gray-50 px-4 py-10 sm:px-8">
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Header */}
        <header className="text-center flex flex-col items-center space-y-2">
          <h1 className="text-2xl sm:text-3xl font-bold text-[#414095]">
            Device Manager Dashboard
          </h1>
          <p className="text-[#428fda] text-sm sm:text-base">
            Manage users, devices, and payments all in one place.
          </p>
        </header>

        {/* Dashboard Cards */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-6">
          <Card className="shadow-lg hover:shadow-2xl transition-shadow bg-gradient-to-r from-[#e2e4f7] to-[#d6ebfa] border border-[#428fda] rounded-xl">
            <CardContent className="p-6 flex flex-col items-start gap-4">
              <h2 className="text-xl font-semibold text-[#414095]">🔍 Search Devices/Users</h2>
              <p className="text-gray-600 text-sm">
                Look up any device or user profile by ID, email or name.
              </p>
              <Link href="/search" className="mt-auto w-full">
                <Button className="w-full bg-[#428fda] hover:bg-[#414095] text-white">
                  Go to Search
                </Button>
              </Link>
            </CardContent>
          </Card>

          <Card className="shadow-lg hover:shadow-2xl transition-shadow bg-gradient-to-r from-[#e2e4f7] to-[#d6ebfa] border border-[#428fda] rounded-xl">
            <CardContent className="p-6 flex flex-col items-start gap-4">
              <h2 className="text-xl font-semibold text-[#414095]">➕ Add New Device</h2>
              <p className="text-gray-600 text-sm">
                Add devices in bulk or one by one. Max 15 at a time for bulk.
              </p>
              <Link href="/add-device" className="mt-auto w-full">
                <Button className="w-full bg-[#428fda] hover:bg-[#414095] text-white">
                  Add Device
                </Button>
              </Link>
            </CardContent>
          </Card>

          <Card className="shadow-lg hover:shadow-2xl transition-shadow bg-gradient-to-r from-[#e2e4f7] to-[#d6ebfa] border border-[#428fda] rounded-xl">
            <CardContent className="p-6 flex flex-col items-start gap-4">
              <h2 className="text-xl font-semibold text-[#414095]">👤 Onboard New User</h2>
              <p className="text-gray-600 text-sm">
                Register a new user by name, phone and email.
              </p>
              <Link href="/onboard_user" className="mt-auto w-full">
                <Button className="w-full bg-[#428fda] hover:bg-[#414095] text-white">
                  Onboard User
                </Button>
              </Link>
            </CardContent>
          </Card>

          <Card className="shadow-lg hover:shadow-2xl transition-shadow bg-gradient-to-r from-[#e2e4f7] to-[#d6ebfa] border border-[#428fda] rounded-xl">
            <CardContent className="p-6 flex flex-col items-start gap-4">
              <h2 className="text-xl font-semibold text-[#414095]">💳 Finance</h2>
              <p className="text-gray-600 text-sm">
                Track payments, billing, and transaction history.
              </p>
              <Link href="/finance" className="mt-auto w-full">
                <Button className="w-full bg-gray-300 text-gray-700 cursor-not-allowed" disabled>
                  Coming Soon
                </Button>
              </Link>
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
