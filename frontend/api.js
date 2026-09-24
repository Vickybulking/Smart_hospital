/* Set window.CARELY_CONFIG after deployment, for example:
   window.CARELY_CONFIG = { apiUrl: 'https://.../development' };
   A Cognito/Amplify sign-in should store the ID token as carely_id_token.
*/
window.CARELY_CONFIG = window.CARELY_CONFIG || { apiUrl: '' };

async function carelyApi(path, options = {}) {
  const token = localStorage.getItem('carely_id_token');
  if (!window.CARELY_CONFIG.apiUrl || !token) return null;
  const response = await fetch(`${window.CARELY_CONFIG.apiUrl}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...(options.headers || {}) },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'API request failed');
  return body;
}
