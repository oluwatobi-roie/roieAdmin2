// src/app/login/layout.tsx
import { Geist, Geist_Mono } from "next/font/google";
import "../globals.css"; // correct relative path

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return (
    <section
      className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen flex items-center justify-center bg-gray-50`}
    >
      {children}
    </section>
  );
}
