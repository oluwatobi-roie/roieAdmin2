export async function checkSession() {
  try {
    const res = await fetch("/api/auth/check-session", {
      method: "GET",
      credentials: "include", // 🔑 sends HttpOnly cookie
    });

    if (!res.ok) return { authenticated: false };

    return await res.json();
  } catch (err) {
    console.error("Session check error:", err);
    return { authenticated: false };
  }
}
