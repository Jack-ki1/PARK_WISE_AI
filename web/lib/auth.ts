/** Session-scoped API key management.
 * Stored in sessionStorage only to protect keys from persistent XSS exfiltration.
 */
const API_KEY_SESSION = "parkwise-session-api-key";

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(API_KEY_SESSION);
  } catch {
    return null;
  }
}

export function setSessionApiKey(key: string): void {
  if (typeof window === "undefined") return;
  try {
    if (key.trim()) {
      window.sessionStorage.setItem(API_KEY_SESSION, key.trim());
    } else {
      window.sessionStorage.removeItem(API_KEY_SESSION);
    }
  } catch {
    // SessionStorage may be restricted in private/sandbox frames
  }
}

export function clearSessionApiKey(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(API_KEY_SESSION);
  } catch {
    // No-op
  }
}
