"use client";

import { useState, useEffect } from "react";
import { useAuth } from "../hooks/useAuth";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FiMail, FiLock, FiEye, FiEyeOff } from "react-icons/fi";
import Image from "next/image";
import { useRouter } from 'next/navigation';

export default function LoginPage() {
  const { authenticated } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState("");
  const router = useRouter();

  useEffect(() => {
    if (authenticated) router.push("/");
  }, [authenticated, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setFeedback("");

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setFeedback(data.error || "Login failed");
      } else {
        router.push('/');
      }
    } catch (err) {
      console.error(err);
      setFeedback("Unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen w-full flex flex-col items-center justify-center bg-gradient-to-br from-gray-100 to-gray-200 px-4 py-10">
      
      {/* Logo on top of the card */}
      <div className="mb-8 flex justify-center">
        <Image src="/logo.svg" alt="Logo" width={200} height={150} />
      </div>

      {/* Login Card */}
      <Card className="w-full max-w-md shadow-xl rounded-3xl bg-white">
        <CardContent className="p-10 space-y-8">
          <h1 className="text-3xl font-bold text-center text-[#414095]">
            Welcome Back
          </h1>

          {feedback && (
            <p className="text-center text-red-600 font-medium">{feedback}</p>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="relative">
              <label className="flex items-center gap-2 mb-1 text-gray-700 font-medium">
                <FiMail /> Email
              </label>
              <Input
                type="email"
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="pr-10"
              />
            </div>

            <div className="relative">
              <label className="flex items-center gap-2 mb-1 text-gray-700 font-medium">
                <FiLock /> Password
              </label>
              <Input
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="pr-10"
              />
              <button
                type="button"
                className="absolute right-3 top-10 text-gray-500 hover:text-gray-700"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? <FiEyeOff /> : <FiEye />}
              </button>
            </div>

            <Button
              type="submit"
              className="w-full bg-gradient-to-r from-[#428fda] to-[#414095] hover:from-[#414095] hover:to-[#428fda] text-white font-semibold py-3 rounded-xl shadow-md transition-all"
              disabled={loading}
            >
              {loading ? "Logging in..." : "Login"}
            </Button>
          </form>

          <p className="text-center text-sm text-gray-600">
            Don’t have an account?{" "}
            <a
              href="https://wa.me/+2348055302073"
              className="text-[#428fda] hover:underline"
            >
              Chat with us on WhatsApp
            </a>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
