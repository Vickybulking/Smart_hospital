/* Carely authentication — Amazon Cognito (amazon-cognito-identity-js SDK).
   Wraps sign-in / sign-up / verification / sign-out and exposes the current
   session's ID token and claims. No credentials are ever stored in code. */

(function () {
  const C = window.AmazonCognitoIdentity;

  function configured() {
    const cfg = window.CARELY_CONFIG || {};
    return Boolean(cfg.userPoolId && cfg.userPoolClientId && cfg.region);
  }

  function pool() {
    return new C.CognitoUserPool({
      UserPoolId: window.CARELY_CONFIG.userPoolId,
      ClientId: window.CARELY_CONFIG.userPoolClientId,
    });
  }

  function decodeJwtPayload(token) {
    try {
      const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      return JSON.parse(atob(payload));
    } catch (e) {
      return {};
    }
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
      const groups = payload['cognito:groups'] || [];
      return {
        sub: payload['sub'],
        email: payload['email'] || '',
        name: payload['name'] || '',
        groups,
        role: groups.includes('admin') ? 'admin' : groups.includes('doctor') ? 'doctor' : groups.includes('patient') ? 'patient' : null,
      };
    },
  };
})();
