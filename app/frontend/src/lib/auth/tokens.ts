export function decodeAccessTokenExp(token: string): number | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const raw = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = raw + "=".repeat((4 - (raw.length % 4)) % 4);
    const payload = JSON.parse(atob(padded)) as Record<string, unknown>;
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

// Returns seconds until expiry; negative if already expired.
export function tokenTtlSeconds(token: string): number {
  const exp = decodeAccessTokenExp(token);
  if (exp === null) return -1;
  return exp - Math.floor(Date.now() / 1000);
}
