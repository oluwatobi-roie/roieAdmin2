"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FiMail, FiLock } from "react-icons/fi";
import Image from "next/image";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState("");

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
        alert("Logged in successfully!");
        // Add redirect/session logic here
      }
    } catch (err) {
      console.error(err);
      setFeedback("Unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-8 sm:px-6 md:px-12">
      <Card className="w-full max-w-md shadow-lg rounded-2xl bg-white">
        <CardContent className="p-8 space-y-6">
          <div className="flex justify-center mb-6">
            <Image src="/logo.png" alt="Logo" width={120} height={120} />
          </div>

          <h1 className="text-2xl sm:text-3xl font-bold text-[#414095] text-center">
            Login
          </h1>

          {feedback && <p className="text-center text-red-600">{feedback}</p>}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-gray-700 flex items-center gap-2 mb-1">
                <FiMail /> Email
              </label>
              <Input
                type="email"
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 flex items-center gap-2 mb-1">
                <FiLock /> Password
              </label>
              <Input
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <Button
              type="submit"
              className="w-full bg-[#414095] hover:bg-[#428fda] text-white"
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
