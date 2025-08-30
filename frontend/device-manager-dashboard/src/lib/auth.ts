export async function checkSession() {
  try {
    const res = await fetch("http://127.0.0.1:5000/api/auth/check-session", {
      method: "GET",
      credentials: "include", // 🔑 sends HttpOnly cookie
    });

    if (!res.ok) return { authenticated: false };

    return await res.json();
  } catch (err) {
    return { authenticated: false };
  }
}
