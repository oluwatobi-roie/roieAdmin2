'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

export function useAuth() {
  const [auth_loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await fetch('/api/auth/check-session', { method: 'GET' });
        if (res.ok) {
          const data = await res.json();
          if (data.authenticated) {
            setAuthenticated(true);
          } else {
            router.replace('/login');
          }
        } else {
          router.replace('/login');
        }
      } catch (err) {
        console.error('Auth check failed:', err);
        router.replace('/login');
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, [router]);

  return { auth_loading, authenticated };
}
