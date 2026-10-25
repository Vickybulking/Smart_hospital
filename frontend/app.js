/* Carely application — real AWS backend (Cognito + API Gateway + Lambda + DynamoDB).
   Every screen renders from live API data; failures are surfaced explicitly. */

const state = {
  session: null,
  claims: null,
  role: null,
  page: 'overview',
  patientProfile: null,     // caller's own patient profile (patient role)
  doctorProfile: null,      // caller's own doctor profile (doctor role)
  doctors: [],              // all doctor profiles (booking + admin)
  appointments: [],         // role-scoped appointments
};

const DAY_NAMES = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];

/* ── small utilities ─────────────────────────────────────────────────────── */

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function initials(name) {
  return String(name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  return d.toLocaleString(undefined, {
    weekday: 'short', day: 'numeric', month: 'short',
    hour: 'numeric', minute: '2-digit', hour12: true,
  });
}

function toast(message, isError = false) {
  const host = document.getElementById('toast-host');
  if (!host) return alert(message);
  const el = document.createElement('div');
  el.className = `toast ${isError ? 'toast-error' : ''}`;
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => el.remove(), isError ? 6000 : 3200);
}

function spinner(label = 'Loading…') {
  return `<div class="loading-box"><span class="spin"></span> ${esc(label)}</div>`;
}

function apiErrorBox(err) {
  return `<div class="alert notice">${esc(err.message || 'Request failed')}</div>`;
}

async function guard(fn) {
  try {
    return { html: await fn() };
  } catch (err) {
    console.error('[Carely]', err.message);
    return { html: apiErrorBox(err) };
  }
}

/* ── login / signup ──────────────────────────────────────────────────────── */

function renderLogin(mode = 'signin', message = '') {
  const unconfigured = !backendConfigured();
  document.getElementById('app').innerHTML = `
    <main class="login-wrap">
      <section class="login">
        <div class="brand">care<span>ly</span></div>
        <div class="eyebrow">Smart hospital management</div>
        <h1>${mode === 'signup' ? 'Create your account' : mode === 'verify' ? 'Verify your email' : 'Welcome back'}</h1>
        ${message ? `<p class="date">${esc(message)}</p>` : '<p class="date">Sign in to access your secure workspace.</p>'}
        ${unconfigured ? `<div class="alert notice" style="margin:14px 0">Backend not configured. Run <b>scripts/update_frontend_config.sh</b> after deploying the AWS stack.</div>` : ''}
        ${mode === 'signin' ? signInForm() : mode === 'signup' ? signUpForm() : verifyForm()}
        <p class="hint">Sign-up creates a <b>patient</b> account. Doctor and admin access is provisioned by the hospital.</p>
      </section>
    </main>`;
  document.getElementById('toast-host')?.removeEventListener?.();
}

function signInForm() {
  return `
    <label class="date">Email address<input id="login-email" type="email" autocomplete="username"></label>
    <label class="date">Password<input id="login-password" type="password" autocomplete="current-password"></label>
    <button type="button" class="btn" id="btn-signin" onclick="doSignIn()">Sign in →</button>
    <p class="hint"><a href="#" onclick="renderLogin('signup');return false">Create a patient account</a></p>`;
}

function signUpForm() {
  return `
    <label class="date">Full name<input id="su-name" type="text" autocomplete="name"></label>
    <label class="date">Email address<input id="su-email" type="email" autocomplete="email"></label>
    <label class="date">Password<input id="su-password" type="password" autocomplete="new-password"></label>
    <p class="hint" style="text-align:left">Minimum 8 characters with uppercase, lowercase and a number.</p>
    <button type="button" class="btn" id="btn-signup" onclick="doSignUp()">Create account</button>
    <p class="hint"><a href="#" onclick="renderLogin('signin');return false">Back to sign in</a></p>`;
}

function verifyForm() {
  return `
    <label class="date">Verification code<input id="vf-code" type="text" inputmode="numeric" placeholder="123456"></label>
    <button type="button" class="btn" id="btn-verify" onclick="doVerify()">Verify and continue</button>
    <p class="hint"><a href="#" onclick="renderLogin('signin');return false">Back to sign in</a></p>`;
}

async function doSignIn() {
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const btn = document.getElementById('btn-signin');
  if (!email || !password) return toast('Enter your email and password', true);
  btn.disabled = true; btn.textContent = 'Signing in…';
  try {
    const session = await window.carelyAuth.signIn(email, password);
    await enterApp(session);
  } catch (err) {
    btn.disabled = false; btn.textContent = 'Sign in →';
    toast(err.message || 'Sign-in failed', true);
  }
}

let pendingSignupEmail = '';

async function doSignUp() {
  const name = document.getElementById('su-name').value.trim();
  const email = document.getElementById('su-email').value.trim();
  const password = document.getElementById('su-password').value;
  if (!name || !email || !password) return toast('Fill in all fields', true);
  const btn = document.getElementById('btn-signup');
  btn.disabled = true; btn.textContent = 'Creating…';
  try {
    await window.carelyAuth.signUp(email, password, name);
    pendingSignupEmail = email;
    renderLogin('verify', `We emailed a verification code to ${email}.`);
  } catch (err) {
    btn.disabled = false; btn.textContent = 'Create account';
    toast(err.message || 'Sign-up failed', true);
  }
}

async function doVerify() {
  const code = document.getElementById('vf-code').value.trim();
  if (!code) return toast('Enter the code from your email', true);
  const btn = document.getElementById('btn-verify');
  btn.disabled = true; btn.textContent = 'Verifying…';
  try {
    await window.carelyAuth.confirmSignUp(pendingSignupEmail, code);
    renderLogin('signin', 'Email verified — sign in with your new account.');
  } catch (err) {
    btn.disabled = false; btn.textContent = 'Verify and continue';
    toast(err.message || 'Verification failed', true);
  }
}

async function doSignOut() {
  window.carelyAuth.signOut();
  state.session = null; state.claims = null; state.role = null;
  renderLogin('signin');
}

/* ── app shell ───────────────────────────────────────────────────────────── */

const NAV = {
  patient: [
    { id: 'overview', label: 'Overview' },
    { id: 'book', label: 'Book appointment' },
    { id: 'appointments', label: 'My appointments' },
    { id: 'profile', label: 'My profile' },
  ],
  doctor: [
    { id: 'overview', label: 'Overview' },
    { id: 'schedule', label: 'My schedule' },
    { id: 'patients', label: 'My patients' },
    { id: 'queue', label: 'Appointment requests' },
  ],
  admin: [
    { id: 'overview', label: 'Overview' },
    { id: 'doctors', label: 'Doctors' },
    { id: 'patients', label: 'Patients' },
    { id: 'appointments', label: 'Appointments' },
  ],
};

async function enterApp(session) {
  const claims = window.carelyAuth.claims(session);
  if (!claims.role) {
    toast('Your account has no role assigned yet. Contact the administrator.', true);
    window.carelyAuth.signOut();
    return;
  }
  state.session = session;
  state.claims = claims;
  state.role = claims.role;
  state.page = 'overview';
  await render();
}

async function render() {
  const c = state.claims;
  const displayName = c.role === 'doctor' ? `Dr. ${c.name}`.replace('Dr. Dr.', 'Dr.') : c.name;
  const nav = NAV[state.role] || [];
  document.getElementById('app').innerHTML = `
    <div class="shell">
      <aside class="side">
        <div class="brand">care<span>ly</span></div>
        <div class="user">
          <div class="avatar">${initials(c.name)}</div>
          <strong>${esc(displayName)}</strong>
          <small>${c.role[0].toUpperCase() + c.role.slice(1)} account</small>
        </div>
        <nav class="nav">
          ${nav.map(n => `<button class="${state.page === n.id ? 'active' : ''}" onclick="go('${n.id}')">${n.label}</button>`).join('')}
        </nav>
        <button class="logout" onclick="doSignOut()">↪　Sign out</button>
      </aside>
      <main class="main">
        <div class="top">
          <div>
            <div class="eyebrow">Carely hospital portal</div>
            <h1 id="page-title"></h1>
          </div>
          <div class="date">${new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</div>
        </div>
        <div id="page-content">${spinner()}</div>
      </main>
    </div>
    <div id="toast-host"></div>`;
  await renderPage();
}

async function go(page) {
  state.page = page;
  document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));
  const item = (NAV[state.role] || []).find(n => n.id === page);
  if (item) {
    const idx = (NAV[state.role] || []).indexOf(item);
    document.querySelectorAll('.nav button')[idx]?.classList.add('active');
  }
  document.getElementById('page-content').innerHTML = spinner();
  await renderPage();
}

async function renderPage() {
  const content = document.getElementById('page-content');
  const title = document.getElementById('page-title');
  const map = {
    'patient': { overview: [patientOverview, 'Your dashboard'], book: [bookAppointment, 'Book a consultation'], appointments: [patientAppointments, 'My appointments'], profile: [patientProfile, 'My profile'] },
    'doctor': { overview: [doctorOverview, 'Your dashboard'], schedule: [doctorSchedule, 'My schedule'], patients: [doctorPatients, 'My patients'], queue: [doctorQueue, 'Appointment requests'] },
    'admin': { overview: [adminOverview, 'Hospital overview'], doctors: [adminDoctors, 'Manage doctors'], patients: [adminPatients, 'Manage patients'], appointments: [adminAppointments, 'All appointments'] },
  };
  const entry = (map[state.role] || {})[state.page] || map[state.role].overview;
  title.textContent = entry[1];
  const { html } = await guard(entry[0]);
  content.innerHTML = html;
}

/* ── data loaders ────────────────────────────────────────────────────────── */

async function loadDoctors() {
  const res = await carelyApi('/doctors?limit=100');
  state.doctors = res.doctors || [];
  return state.doctors;
}

async function loadAppointments() {
  const res = await carelyApi('/appointments?limit=100');
  state.appointments = res.appointments || [];
  return state.appointments;
}

async function loadPatientProfile() {
  try {
    state.patientProfile = await carelyApi(`/patients/${state.claims.sub}`);
  } catch (err) {
    if (err.status === 404) state.patientProfile = null;
    else throw err;
  }
  return state.patientProfile;
}

async function loadDoctorProfile() {
  try {
    state.doctorProfile = await carelyApi(`/doctors/${state.claims.sub}`);
  } catch (err) {
    if (err.status === 404) state.doctorProfile = null;
    else throw err;
  }
  return state.doctorProfile;
}

function doctorById(id) {
  return state.doctors.find(d => d.doctorId === id);
}

/* ── patient screens ─────────────────────────────────────────────────────── */

function metric(value, label, icon) {
  return `<div class="card metric"><div><small>${label}</small><b>${value}</b></div><div class="icon">${icon}</div></div>`;
}

async function patientOverview() {
  await Promise.all([loadAppointments(), loadDoctors().catch(() => [])]);
  await loadPatientProfile();
  const appts = state.appointments;
  const upcoming = appts.filter(a => a.status !== 'cancelled' && a.status !== 'completed' && new Date(a.dateTime) >= new Date());
  const past = appts.filter(a => a.status === 'completed' || (a.status !== 'cancelled' && new Date(a.dateTime) < new Date()));
  return `
    ${state.patientProfile ? '' : `<div class="alert notice">Complete your patient profile before booking — <a href="#" onclick="go('profile')">set it up now</a>.</div>`}
    <div class="grid">
      ${metric(upcoming.length, 'Upcoming appointments', '◷')}
      ${metric(past.length, 'Completed visits', '✓')}
      ${metric(esc(state.patientProfile?.bloodGroup || '—'), 'Blood group', '♡')}
      <section class="card wide">
        <div class="section-head"><h2>Upcoming appointments</h2>
          <button class="link" onclick="go('appointments')">View all →</button></div>
        ${upcoming.length ? `<table class="table">
          <tr><th>Doctor</th><th>Date &amp; time</th><th>Status</th></tr>
          ${upcoming.slice(0, 5).map(a => `<tr>
            <td><b>${esc(doctorById(a.doctorId)?.name || 'Doctor')}</b><br><small>${esc(doctorById(a.doctorId)?.specialty || '')}</small></td>
            <td>${fmtDateTime(a.dateTime)}</td>
            <td><span class="badge ${a.status === 'confirmed' ? '' : 'gray'}">${esc(a.status)}</span></td>
          </tr>`).join('')}
        </table>` : '<p class="date">No upcoming appointments.</p>'}
      </section>
      <section class="card">
        <div class="section-head"><h2>Quick booking</h2></div>
        <p class="date">Find a specialist and reserve an available slot.</p>
        <button class="btn" onclick="go('book')">Book appointment</button>
      </section>
    </div>`;
}

const bookingSel = { doctorId: '', date: '', slot: '' };

async function bookAppointment() {
  await Promise.all([loadDoctors(), loadAppointments().catch(() => [])]);
  if (!state.doctors.length) return '<div class="alert notice">No doctors are registered yet.</div>';
  bookingSel.doctorId = bookingSel.doctorId || state.doctors[0].doctorId;
  if (!bookingSel.date) {
    const d = new Date(); d.setDate(d.getDate() + 1);
    bookingSel.date = d.toISOString().slice(0, 10);
  }
  const doctor = doctorById(bookingSel.doctorId);
  const availability = doctor?.availability || {};
  const dayName = DAY_NAMES[new Date(`${bookingSel.date}T00:00:00Z`).getUTCDay()];
  const slots = Array.isArray(availability[dayName]) ? availability[dayName] : [];

  // Grey out slots already taken by a pending/confirmed appointment.
  // Slots taken by OTHER patients are not visible to this patient (the
  // backend list is role-scoped) — the authoritative check is the backend's
  // atomic slot lock, which returns 409 if the slot was taken meanwhile.
  const taken = new Set(
    state.appointments
      .filter(a => a.doctorId === bookingSel.doctorId && a.status !== 'cancelled' &&
        String(a.dateTime).slice(0, 10) === bookingSel.date)
      .map(a => String(a.dateTime).slice(11, 16))
  );

  return `
    <section class="card">
      <div class="section-head"><div><div class="eyebrow">Appointment management</div><h2>Book a consultation</h2></div>
        <span class="badge">Live availability</span></div>
      <div class="form">
        <label>1 · Select doctor
          <select id="book-doctor" onchange="bookingSel.doctorId=this.value;bookingSel.slot='';rerenderPage()">
            ${state.doctors.map(d => `<option value="${esc(d.doctorId)}" ${d.doctorId === bookingSel.doctorId ? 'selected' : ''}>${esc(d.name)} — ${esc(d.specialty || 'General')}</option>`).join('')}
          </select>
        </label>
        <label>2 · Select date
          <input type="date" id="book-date" value="${bookingSel.date}" min="${new Date().toISOString().slice(0, 10)}"
            onchange="bookingSel.date=this.value;bookingSel.slot='';rerenderPage()">
        </label>
        <div>
          <label>3 · Available time slots (${esc(dayName)})</label>
          ${slots.length ? `<div class="slots">
            ${slots.map(s => {
              const isTaken = taken.has(s);
              return `<button class="slot ${bookingSel.slot === s ? 'selected' : ''}" ${isTaken ? 'disabled title="Already booked"' : ''}
                onclick="bookingSel.slot='${s}';rerenderPage()">${s}${isTaken ? ' ·' : ''}</button>`;
            }).join('')}
          </div>` : `<p class="date">Dr. ${esc((doctor?.name || '').replace(/^Dr\.?\s*/i, ''))} has no slots listed for ${esc(dayName)}s. Try another day.</p>`}
        </div>
        <label>Reason for visit (optional)<input id="book-reason" placeholder="e.g. Routine follow-up"></label>
        <button class="btn" id="btn-book" onclick="confirmBooking()">Confirm appointment →</button>
      </div>
    </section>`;
}

async function rerenderPage() {
  const content = document.getElementById('page-content');
  if (!content) return;
  const scrollY = window.scrollY;
  if (state.role === 'patient' && state.page === 'book') {
    const { html } = await guard(bookAppointment);
    content.innerHTML = html;
  } else if (state.role === 'doctor' && state.page === 'schedule') {
    const { html } = await guard(doctorSchedule);
    content.innerHTML = html;
  } else {
    await renderPage();
    return;
  }
  window.scrollTo(0, scrollY);
}

async function confirmBooking() {
  if (!bookingSel.slot) return toast('Select an available time slot first', true);
  const btn = document.getElementById('btn-book');
  btn.disabled = true; btn.textContent = 'Booking…';
  const reason = document.getElementById('book-reason')?.value.trim() || '';
  const dateTime = `${bookingSel.date}T${bookingSel.slot}:00Z`;
  try {
    await carelyApi('/appointments', {
      method: 'POST',
      body: JSON.stringify({ patientId: state.claims.sub, doctorId: bookingSel.doctorId, dateTime, reason }),
    });
    toast('Appointment requested — the doctor will confirm shortly.');
    bookingSel.slot = '';
    state.page = 'appointments';
    await render();
  } catch (err) {
    btn.disabled = false; btn.textContent = 'Confirm appointment →';
    if (err.status === 409) toast('That slot was just taken by another patient. Pick a different time.', true);
    else toast(err.message || 'Booking failed', true);
  }
}

async function patientAppointments() {
  await Promise.all([loadAppointments(), loadDoctors().catch(() => [])]);
  const rows = state.appointments
    .slice()
    .sort((a, b) => String(b.dateTime).localeCompare(String(a.dateTime)));
  return `
    <section class="card">
      <div class="section-head"><div><div class="eyebrow">Your care timeline</div><h2>My appointments</h2></div>
        <button class="btn" onclick="go('book')">+ New appointment</button></div>
      ${rows.length ? `<table class="table">
        <tr><th>Doctor</th><th>Date &amp; time</th><th>Reason</th><th>Status</th><th>Action</th></tr>
        ${rows.map(a => `<tr>
          <td><b>${esc(doctorById(a.doctorId)?.name || 'Doctor')}</b><br><small>${esc(doctorById(a.doctorId)?.specialty || '')}</small></td>
          <td>${fmtDateTime(a.dateTime)}</td>
          <td>${esc(a.reason || '—')}</td>
          <td><span class="badge ${a.status === 'confirmed' ? '' : 'gray'}">${esc(a.status)}</span></td>
          <td>${a.status === 'pending' || a.status === 'confirmed' ? `<button class="link" onclick="cancelAppointment('${esc(a.appointmentId)}')">Cancel</button>` : '—'}</td>
        </tr>`).join('')}
      </table>` : '<p class="date">No appointments yet — book your first consultation.</p>'}
    </section>`;
}

async function cancelAppointment(id) {
  if (!confirm('Cancel this appointment?')) return;
  try {
    await carelyApi(`/appointments/${id}`, { method: 'DELETE' });
    toast('Appointment cancelled.');
    await rerenderPage();
  } catch (err) {
    toast(err.message || 'Cancellation failed', true);
  }
}

async function patientProfile() {
  await loadPatientProfile();
  const p = state.patientProfile;
  const c = state.claims;
  if (!p) {
    return `
      <section class="card">
        <div class="section-head"><div><div class="eyebrow">First time here</div><h2>Create your patient profile</h2></div>
          <span class="badge">Private to you</span></div>
        <div class="form">
          <label>Full name<input id="pf-name" value="${esc(c.name)}"></label>
          <label>Email<input id="pf-email" value="${esc(c.email)}"></label>
          <label>Phone<input id="pf-phone" placeholder="+91 98765 43210"></label>
          <label>Date of birth<input id="pf-dob" type="date"></label>
          <label>Blood group<select id="pf-blood"><option value=""></option>
            ${['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map(b => `<option>${b}</option>`).join('')}</select></label>
          <label>Emergency contact<input id="pf-emergency" placeholder="Name · phone"></label>
          <button class="btn" id="btn-pf-save" onclick="savePatientProfile(false)">Save profile →</button>
        </div>
      </section>`;
  }
  return `
    <section class="card">
      <div class="section-head"><div><div class="eyebrow">Your secure profile</div><h2>Patient information</h2></div>
        <span class="badge">Private to you</span></div>
      <div class="form">
        <label>Full name<input id="pf-name" value="${esc(p.name)}"></label>
        <label>Email<input id="pf-email" value="${esc(p.email)}"></label>
        <label>Phone<input id="pf-phone" value="${esc(p.phone || '')}"></label>
        <label>Date of birth<input id="pf-dob" type="date" value="${esc(p.dateOfBirth || '')}"></label>
        <label>Blood group<select id="pf-blood"><option value=""></option>
          ${['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map(b => `<option ${p.bloodGroup === b ? 'selected' : ''}>${b}</option>`).join('')}</select></label>
        <label>Emergency contact<input id="pf-emergency" value="${esc(p.emergencyContact || '')}"></label>
        <button class="btn" id="btn-pf-save" onclick="savePatientProfile(true)">Save changes →</button>
      </div>
      <div class="notice">🔒 Your health information is confidential. Other patients cannot access this profile or your medical records.</div>
    </section>`;
}

async function savePatientProfile(exists) {
  const payload = {
    name: document.getElementById('pf-name').value.trim(),
    email: document.getElementById('pf-email').value.trim(),
    phone: document.getElementById('pf-phone').value.trim(),
    dateOfBirth: document.getElementById('pf-dob').value,
    bloodGroup: document.getElementById('pf-blood').value,
    emergencyContact: document.getElementById('pf-emergency').value.trim(),
  };
  if (!payload.name || !payload.email) return toast('Name and email are required', true);
  const btn = document.getElementById('btn-pf-save');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    if (exists) await carelyApi(`/patients/${state.claims.sub}`, { method: 'PUT', body: JSON.stringify(payload) });
    else await carelyApi('/patients', { method: 'POST', body: JSON.stringify(payload) });
    toast('Profile saved.');
    await rerenderPage();
  } catch (err) {
    btn.disabled = false; btn.textContent = exists ? 'Save changes →' : 'Save profile →';
    toast(err.message || 'Save failed', true);
  }
}

/* ── doctor screens ──────────────────────────────────────────────────────── */

async function doctorOverview() {
  await Promise.all([loadAppointments(), loadDoctorProfile()]);
  const pending = state.appointments.filter(a => a.status === 'pending');
  const confirmed = state.appointments.filter(a => a.status === 'confirmed');
  const patients = new Set(state.appointments.map(a => a.patientId));
  return `
    ${state.doctorProfile ? '' : `<div class="alert notice">You have no doctor profile yet — <a href="#" onclick="go('schedule')">set up your profile and availability</a>.</div>`}
    <div class="grid">
      ${metric(confirmed.length, 'Confirmed appointments', '◷')}
      ${metric(pending.length, 'Pending requests', '!')}
      ${metric(patients.size, 'Patients', '♙')}
      <section class="card wide">
        <div class="section-head"><h2>Next appointments</h2>
          <button class="link" onclick="go('queue')">Manage queue →</button></div>
        ${confirmed.length ? `<table class="table"><tr><th>Patient</th><th>Date &amp; time</th><th>Status</th></tr>
          ${confirmed.slice(0, 5).map(a => `<tr><td>Patient ${esc(a.patientId.slice(0, 8))}</td><td>${fmtDateTime(a.dateTime)}</td><td><span class="badge">${esc(a.status)}</span></td></tr>`).join('')}
        </table>` : '<p class="date">No confirmed appointments yet.</p>'}
      </section>
      <section class="card">
        <div class="section-head"><h2>Availability</h2></div>
        <p class="date">${state.doctorProfile?.availability ? Object.entries(state.doctorProfile.availability).filter(([, v]) => v.length).map(([d]) => d[0].toUpperCase() + d.slice(1)).join(', ') || 'Not set' : 'Profile missing'}</p>
        <button class="btn secondary" onclick="go('schedule')">Edit schedule</button>
      </section>
    </div>`;
}

async function doctorSchedule() {
  await loadDoctorProfile();
  if (!state.doctorProfile) {
    return `
      <section class="card">
        <div class="section-head"><div><div class="eyebrow">One-time setup</div><h2>Create your doctor profile</h2></div></div>
        <div class="form">
          <label>Full name<input id="dp-name" value="${esc(state.claims.name)}"></label>
          <label>Email<input id="dp-email" value="${esc(state.claims.email)}"></label>
          <label>Specialty<input id="dp-specialty" placeholder="e.g. Cardiology"></label>
          <label>Qualification<input id="dp-qual" placeholder="e.g. MBBS, MD"></label>
          <label>Years of experience<input id="dp-exp" placeholder="e.g. 12"></label>
          <button class="btn" id="btn-dp-save" onclick="saveDoctorProfile()">Save profile →</button>
        </div>
      </section>`;
  }
  const avail = state.doctorProfile.availability || {};
  return `
    <section class="card">
      <div class="section-head"><div><div class="eyebrow">Weekly schedule</div><h2>My availability</h2></div>
        <span class="badge">${state.doctorProfile.specialty || ''}</span></div>
      <p class="date">Enter times as 24-hour HH:MM, comma-separated. Example: <code>09:00, 10:30, 14:00</code></p>
      <div class="form">
        ${DAY_NAMES.filter(d => d !== 'sunday' || true).map(day => `
          <label>${day[0].toUpperCase() + day.slice(1)}
            <input id="avail-${day}" value="${esc((avail[day] || []).join(', '))}" placeholder="09:00, 10:30">
          </label>`).join('')}
        <button class="btn" id="btn-avail-save" onclick="saveAvailability()">Save availability →</button>
      </div>
      <div class="notice">Patients can only book the exact slots you list here. Booked slots are removed automatically.</div>
    </section>`;
}

async function saveDoctorProfile() {
  const payload = {
    name: document.getElementById('dp-name').value.trim(),
    email: document.getElementById('dp-email').value.trim(),
    specialty: document.getElementById('dp-specialty').value.trim(),
    qualification: document.getElementById('dp-qual').value.trim(),
    experience: document.getElementById('dp-exp').value.trim(),
  };
  if (!payload.name || !payload.email || !payload.specialty) return toast('Name, email and specialty are required', true);
  const btn = document.getElementById('btn-dp-save');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    await carelyApi('/doctors', { method: 'POST', body: JSON.stringify(payload) });
    toast('Doctor profile saved.');
    await rerenderPage();
  } catch (err) {
    btn.disabled = false; btn.textContent = 'Save profile →';
    toast(err.message || 'Save failed', true);
  }
}

async function saveAvailability() {
  const availability = {};
  const timeRe = /^([01]\d|2[0-3]):([0-5]\d)$/;
  for (const day of DAY_NAMES) {
    const raw = document.getElementById(`avail-${day}`).value.trim();
    if (!raw) { availability[day] = []; continue; }
    const times = raw.split(',').map(t => t.trim()).filter(Boolean);
    for (const t of times) {
      if (!timeRe.test(t)) return toast(`Invalid time "${t}" for ${day} — use HH:MM (24-hour)`, true);
    }
    availability[day] = times;
  }
  const btn = document.getElementById('btn-avail-save');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    await carelyApi(`/doctors/${state.claims.sub}/availability`, {
      method: 'PUT', body: JSON.stringify({ availability }),
    });
    toast('Availability updated.');
    await rerenderPage();
  } catch (err) {
    btn.disabled = false; btn.textContent = 'Save availability →';
    toast(err.message || 'Save failed', true);
  }
}

async function doctorQueue() {
  await loadAppointments();
  const pending = state.appointments.filter(a => a.status === 'pending')
    .sort((a, b) => String(a.dateTime).localeCompare(String(b.dateTime)));
  const decided = state.appointments.filter(a => a.status !== 'pending')
    .sort((a, b) => String(b.dateTime).localeCompare(String(a.dateTime)));
  return `
    <section class="card">
      <div class="section-head"><div><div class="eyebrow">Today's queue</div><h2>Appointment requests</h2></div>
        <span class="badge">${pending.length} pending</span></div>
      ${pending.length ? `<table class="table">
        <tr><th>Patient</th><th>Date &amp; time</th><th>Reason</th><th>Action</th></tr>
        ${pending.map(a => `<tr>
          <td>Patient ${esc(a.patientId.slice(0, 8))}</td>
          <td>${fmtDateTime(a.dateTime)}</td>
          <td>${esc(a.reason || '—')}</td>
          <td><button class="btn" onclick="decideAppointment('${esc(a.appointmentId)}', 'confirmed')">Accept</button>
              <button class="link" onclick="decideAppointment('${esc(a.appointmentId)}', 'declined')">Decline</button></td>
        </tr>`).join('')}
      </table>` : '<p class="date">No pending requests.</p>'}
      ${decided.length ? `<div class="section-head" style="margin-top:22px"><h2>Recent decisions</h2></div>
        <table class="table"><tr><th>Patient</th><th>Date &amp; time</th><th>Status</th></tr>
          ${decided.slice(0, 8).map(a => `<tr><td>Patient ${esc(a.patientId.slice(0, 8))}</td><td>${fmtDateTime(a.dateTime)}</td>
            <td><span class="badge ${a.status === 'confirmed' ? '' : 'gray'}">${esc(a.status)}</span></td></tr>`).join('')}
        </table>` : ''}
    </section>`;
}

async function decideAppointment(id, decision) {
  try {
    await carelyApi(`/appointments/${id}/approval`, { method: 'PUT', body: JSON.stringify({ decision }) });
    toast(decision === 'confirmed' ? 'Appointment confirmed — patient notified.' : 'Appointment declined — patient notified.');
    await rerenderPage();
  } catch (err) {
    toast(err.message || 'Update failed', true);
  }
}

async function doctorPatients() {
  await loadAppointments();
  const byPatient = new Map();
  for (const a of state.appointments) {
    if (!byPatient.has(a.patientId)) byPatient.set(a.patientId, []);
    byPatient.get(a.patientId).push(a);
  }
  const names = {};
  await Promise.all([...byPatient.keys()].map(async pid => {
    try { names[pid] = (await carelyApi(`/patients/${pid}`)).name; } catch (e) { names[pid] = null; }
  }));
  return `
    <section class="card">
      <div class="section-head"><h2>My patients</h2><span class="badge">Privacy protected</span></div>
      ${byPatient.size ? `<table class="table">
        <tr><th>Patient</th><th>Appointments</th><th>Next visit</th></tr>
        ${[...byPatient.entries()].map(([pid, appts]) => {
          const next = appts.filter(a => a.status !== 'cancelled' && new Date(a.dateTime) >= new Date())
            .sort((a, b) => String(a.dateTime).localeCompare(String(b.dateTime)))[0];
          return `<tr><td><b>${esc(names[pid] || `Patient ${pid.slice(0, 8)}`)}</b></td>
            <td>${appts.length}</td><td>${next ? fmtDateTime(next.dateTime) : '—'}</td></tr>`;
        }).join('')}
      </table>` : '<p class="date">No patients yet — they appear here once they book with you.</p>'}
    </section>`;
}

/* ── admin screens ───────────────────────────────────────────────────────── */

async function adminOverview() {
  const [doctors, patients, appointments] = await Promise.all([
    carelyApi('/doctors?limit=100'), carelyApi('/patients?limit=100'), carelyApi('/appointments?limit=100'),
  ]);
  const docList = doctors.doctors || [];
  return `
    <div class="grid">
      ${metric((patients.patients || []).length, 'Registered patients', '♙')}
      ${metric(docList.length, 'Active doctors', '✚')}
      ${metric((appointments.appointments || []).length, 'Appointments', '◷')}
      <section class="card wide">
        <div class="section-head"><h2>Doctor profiles</h2>
          <button class="link" onclick="go('doctors')">Manage doctors →</button></div>
        ${docList.map(d => `<div class="doctor">
          <div class="doc-avatar">${initials(d.name)}</div>
          <div><b>${esc(d.name)}</b><p>${esc(d.specialty || '')} · ${esc(d.experience || '')}</p></div>
        </div>`).join('') || '<p class="date">No doctors registered.</p>'}
      </section>
      <section class="card">
        <h2>System activity</h2>
        <p class="date">Latest appointment events</p>
        ${(appointments.appointments || []).slice(0, 6).map(a =>
          `<p>● <b>${esc(a.status)}</b> · ${fmtDateTime(a.updatedAt || a.dateTime)}</p>`).join('') || '<p class="date">No activity yet.</p>'}
      </section>
    </div>`;
}

async function adminDoctors() {
  await loadDoctors();
  return `
    <section class="card">
      <div class="section-head"><h2>Manage doctors</h2></div>
      ${state.doctors.length ? `<table class="table">
        <tr><th>Doctor</th><th>Specialty</th><th>Contact</th><th>Availability days</th></tr>
        ${state.doctors.map(d => `<tr>
          <td><b>${esc(d.name)}</b><br><small>${esc(d.doctorId.slice(0, 8))}</small></td>
          <td>${esc(d.specialty || '—')}</td>
          <td>${esc(d.email || '—')}</td>
          <td>${Object.entries(d.availability || {}).filter(([, v]) => v && v.length).map(([day]) => day.slice(0, 3)).join(', ') || '—'}</td>
        </tr>`).join('')}
      </table>` : '<p class="date">No doctors yet. Doctors create their own profiles after their Cognito account is provisioned.</p>'}
      <div class="notice">🔒 Doctor Cognito accounts are provisioned with <code>scripts/seed_data.py</code>; new self sign-ups always land in the patient group.</div>
    </section>`;
}

async function adminPatients() {
  const res = await carelyApi('/patients?limit=100');
  const patients = res.patients || [];
  return `
    <section class="card">
      <div class="section-head"><h2>Manage patient accounts</h2><span class="badge">${patients.length} registered</span></div>
      ${patients.length ? `<table class="table">
        <tr><th>Patient</th><th>Contact</th><th>Blood group</th><th>Registered</th></tr>
        ${patients.map(p => `<tr>
          <td><b>${esc(p.name)}</b><br><small>${esc(p.patientId.slice(0, 8))}</small></td>
          <td>${esc(p.email || '—')}<br>${esc(p.phone || '')}</td>
          <td>${esc(p.bloodGroup || '—')}</td>
          <td>${fmtDateTime(p.createdAt)}</td>
        </tr>`).join('')}
      </table>` : '<p class="date">No patient profiles yet.</p>'}
      <div class="notice">🔒 Admin access is audited. Patient records remain restricted to authorized hospital users.</div>
    </section>`;
}

async function adminAppointments() {
  await Promise.all([loadAppointments(), loadDoctors().catch(() => [])]);
  const rows = state.appointments.slice().sort((a, b) => String(b.dateTime).localeCompare(String(a.dateTime)));
  return `
    <section class="card">
      <div class="section-head"><h2>All appointments</h2><span class="badge">${rows.length} total</span></div>
      ${rows.length ? `<table class="table">
        <tr><th>Patient</th><th>Doctor</th><th>Date &amp; time</th><th>Status</th></tr>
        ${rows.map(a => `<tr>
          <td>${esc(a.patientId.slice(0, 8))}</td>
          <td>${esc(doctorById(a.doctorId)?.name || a.doctorId.slice(0, 8))}</td>
          <td>${fmtDateTime(a.dateTime)}</td>
          <td><span class="badge ${a.status === 'confirmed' ? '' : 'gray'}">${esc(a.status)}</span></td>
        </tr>`).join('')}
      </table>` : '<p class="date">No appointments booked yet.</p>'}
    </section>`;
}

/* ── boot ────────────────────────────────────────────────────────────────── */

(async function boot() {
  if (!window.carelyAuth.configured()) {
    renderLogin('signin');
    return;
  }
  const session = await window.carelyAuth.getSession();
  if (session) await enterApp(session);
  else renderLogin('signin');
})();
