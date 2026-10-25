/* Carely authentication — Amazon Cognito (amazon-cognito-identity-js SDK).
   Wraps sign-in / sign-up / verification / sign-out and exposes the current
   session's ID token and claims. No credentials are ever stored in code. */

(function () {
  const C = window.AmazonCognitoIdentity;
  const CFG = window.CARELY_CONFIG || {};

  function decodeJwtPayload(token) {
    try {
      const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      return JSON.parse(atob(payload));
    } catch (e) {
      return {};
    }
  }

  function claimsFromPayload(payload) {
    const groups = payload['cognito:groups'] || [];
    return {
      sub: payload['sub'],
      email: payload['email'] || '',
      name: payload['name'] || '',
      groups,
      role: groups.includes('admin') ? 'admin' : groups.includes('doctor') ? 'doctor' : groups.includes('patient') ? 'patient' : null,
    };
  }

  /* ── LOCAL DEV MODE ────────────────────────────────────────────────────────
     Active ONLY when CARELY_CONFIG.localMode is true. Cognito is replaced by
     an in-browser shim (no AWS calls); the backend endpoints must be served
     by scripts/local_dev_server.py, which runs the REAL Lambda handlers
     against a local DynamoDB emulation. */
  if (CFG.localMode) {
    const USERS = CFG.localUsers || {};
    const SESSION_KEY = 'carely_local_session';

    const b64url = (obj) =>
      btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

    const makeSession = (u) => {
      const token = [
        b64url({ alg: 'none', typ: 'JWT' }),
        b64url({ sub: u.sub, email: u.email, name: u.name, 'cognito:groups': [u.role] }),
        'localsig',
      ].join('.');
      return { getIdToken: () => ({ getJwtToken: () => token }) };
    };

    window.carelyAuth = {
      configured: () => true,

      signIn(email, password) {
        return new Promise((resolve, reject) => {
          const u = USERS[email];
          if (!u || password !== u.password) {
            reject(new Error('Local mode: unknown account or wrong password'));
          } else {
            localStorage.setItem(SESSION_KEY, JSON.stringify({ email: u.email }));
            resolve(makeSession(u));
          }
        });
      },

      signUp: () => Promise.reject(new Error('Sign-up is disabled in local dev mode')),
      confirmSignUp: () => Promise.reject(new Error('Sign-up is disabled in local dev mode')),

      signOut() { localStorage.removeItem(SESSION_KEY); },

      getSession() {
        return new Promise((resolve) => {
          const raw = localStorage.getItem(SESSION_KEY);
          const u = raw && USERS[JSON.parse(raw).email];
          resolve(u ? makeSession(u) : null);
        });
      },

      idToken: (session) => (session ? session.getIdToken().getJwtToken() : null),
      claims: (session) => claimsFromPayload(decodeJwtPayload(session.getIdToken().getJwtToken())),
    };

    console.info('[Carely] LOCAL DEV MODE — Cognito/AWS mocked; API handlers run locally via scripts/local_dev_server.py');
    return;
  }

  function configured() {
    return Boolean(CFG.userPoolId && CFG.userPoolClientId && CFG.region);
  }

  function pool() {
    return new C.CognitoUserPool({
      UserPoolId: window.CARELY_CONFIG.userPoolId,
      ClientId: window.CARELY_CONFIG.userPoolClientId,
    });
  }

  function cognitoUser(email) {
    return new C.CognitoUser({ Username: email, Pool: pool() });
  }

  /* ---- Public API ---- */
  window.carelyAuth = {
    configured,

    signIn(email, password) {
      return new Promise((resolve, reject) => {
        const details = new C.AuthenticationDetails({ Username: email, Password: password });
        cognitoUser(email).authenticateUser(details, {
          onSuccess: (session) => resolve(session),
          onFailure: (err) => reject(err),
          newPasswordRequired: () => reject(new Error('Password reset required — contact your administrator.')),
        });
      });
    },

    signUp(email, password, name) {
      return new Promise((resolve, reject) => {
        pool().signUp(
          email,
          password,
          [{ Name: 'email', Value: email }, { Name: 'name', Value: name }],
          [],
          (err, result) => (err ? reject(err) : resolve(result))
        );
      });
    },

    confirmSignUp(email, code) {
      return new Promise((resolve, reject) => {
        cognitoUser(email).confirmRegistration(code, true, (err, result) =>
          err ? reject(err) : resolve(result)
        );
      });
    },

    signOut() {
      try { pool().getCurrentUser()?.signOut(); } catch (e) { /* best effort */ }
    },

    /* Resolve the current session, silently refreshing tokens if expired.
       Returns null when nobody is signed in. */
    getSession() {
      return new Promise((resolve) => {
        const user = pool().getCurrentUser();
        if (!user) return resolve(null);
        user.getSession((err, session) => {
          if (err || !session || !session.isValid()) return resolve(null);
          resolve(session);
        });
      });
    },

    idToken(session) {
      return session ? session.getIdToken().getJwtToken() : null;
    },

    /* Caller info derived from the ID token claims. */
    claims(session) {
      const payload = session ? decodeJwtPayload(session.getIdToken().getJwtToken()) : {};
      return claimsFromPayload(payload);
    },
  };
})();
