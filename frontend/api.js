/* Carely API client — calls the real API Gateway backend.
   There is NO mock-data fallback: if the backend is unreachable or the
   request fails, the error is surfaced to the UI explicitly. */

window.CARELY_CONFIG = window.CARELY_CONFIG || { apiUrl: '' };

function backendConfigured() {
  return Boolean(window.CARELY_CONFIG && window.CARELY_CONFIG.apiUrl);
}

async function carelyApi(path, options = {}) {
  if (!backendConfigured()) {
    throw new Error('Backend not configured — run scripts/update_frontend_config.sh after deploying.');
  }
  const session = await window.carelyAuth.getSession();
  const token = window.carelyAuth.idToken(session);
  if (!token) throw new Error('Not signed in');

  const response = await fetch(`${window.CARELY_CONFIG.apiUrl}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });

  let body = null;
  try { body = await response.json(); } catch (e) { /* non-JSON error body */ }

  if (!response.ok) {
    const message =
      (body && (body.error || (body.errors && body.errors.join('; ')))) ||
      `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}
