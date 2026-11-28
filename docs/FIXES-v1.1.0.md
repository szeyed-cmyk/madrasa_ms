# Problems found in v1.0 and how v1.1.0 fixes them

Every item below was found while reviewing and testing v1.0. Each fix is covered by the test suite in `Madrasa Admin Project/tests/` (241 tests in 1.1.0; 248 after the packaging fixes).

## Critical security
1. **Anyone could log in as admin without a password.** The login cookie was just `user=<username>`, unsigned. Setting a cookie `user=admin` in the browser gave full admin access. **Fix:** signed, HttpOnly, SameSite=Lax session cookies (Starlette `SessionMiddleware`, secret key from `.env` or auto-generated). Sessions are tied to the password, so changing it logs out other sessions. A disabled user is logged out at once.
2. **Missing role checks.** In v1.0 any logged-in user, including a student account, could:
   - save attendance;
   - send SMS to any number;
   - list every student with guardian phones;
   - read every payment, receipt and result;
   - read fee totals on the dashboard;
   - open any student profile.

   **Fix:** every API route now checks login and role (admin / teacher / student). Students can only see their own record and published results. Tests cover every route.
3. **No CSRF protection:** another website could make a logged-in admin's browser change data. **Fix:** a per-session CSRF token is required on every write (API header and form field). Logout is POST-only.
4. **Stored XSS in printing.** Receipt, profile and result printing wrote student names, school name and logo into a new window with `document.write` without escaping. A student named `<script>…` or a crafted logo value ran code with admin rights. **Fix:** printing uses server-rendered, auto-escaped pages (`/print/...`). The logo must be a real PNG, JPEG, GIF or WebP (checked by file signature, max 300 KB); SVG is rejected.
5. **Weak passwords and default credentials.**
   - The default demo passwords were always shown on the login page. (Since 1.1.1 there are no default
     passwords at all: the administrator is created on the first-run setup page.)
   - The `must_change_password` flag was never enforced.
   - Student logins defaulted to `student123`.
   - Passwords as short as 4 characters were allowed, and changing a password did not ask for the current one.

   **Fix:**
   - Forced password change at first login (API returns 403 and pages redirect until it is done).
   - Minimum 8 characters, and common passwords are blocked.
   - The current password is required to change it.
   - Temporary student passwords are random.
   - The login-page hint only shows while the defaults are still in use.
6. **Password check was not constant-time** and used 100k PBKDF2 iterations. **Fix:** `hmac.compare_digest` and 600k iterations. Old hashes still work and are upgraded at the next login.
7. **No brute-force protection.** **Fix:** after 5 failed logins per IP and username, logins are locked for 10 minutes.
8. **Vulnerable dependencies.** pip-audit found 17 known vulnerabilities in the pinned versions: python-multipart 0.0.12 (7), Jinja2 3.1.4 (3), and Starlette 0.38.6 (7, pulled in by FastAPI 0.115). **Fix:** everything is updated and pinned. `pip-audit` reports no known vulnerabilities.
9. **No security headers; API docs were public.** **Fix:** Content-Security-Policy, X-Frame-Options DENY, nosniff, Referrer-Policy and no-store on API responses. `/docs` and `/openapi.json` are disabled.
10. **The server listened on all network interfaces by default (0.0.0.0).** **Fix:** the default is 127.0.0.1. Set `HOST=0.0.0.0` for LAN use.
11. **The database sat next to the code** and was easy to ship by mistake. **Fix:** it now lives in `data/madrasa.db`, which is git-ignored and excluded from packages.

## Crashes and wrong data
12. **`/api/results` was defined twice.** The first version was dead code, and it filtered `status == "active"` (lowercase), which never matched.
13. **Results and profiles were empty for the seeded students.** Marks existed, but there were no subject assignments. **Fix:** subjects are assigned through class defaults. Older databases are repaired on start.
14. **Attendance re-opened as "all Present".** Opening a saved day showed everyone Present, so pressing Save wiped the recorded absences. **Fix:** saved statuses load back, and a banner shows that the day was already saved.
15. **Attendance input had no validation.** A missing field crashed with HTTP 500 (KeyError), and statuses, dates, future dates and unknown students were all accepted. Duplicate rows per day were possible. **Fix:** inputs are validated and there is one row per student per day.
16. **"SMS Absents" ignored saved data.** It sent messages from the unsaved screen to any number. **Fix:** the server builds messages from saved absences and guardian phones only.
17. **Marks ignored the exam.** Saving a mark updated whatever exam row came first, and new marks went to the first exam. There was no range check: negative marks, marks above full marks and text all caused 500 errors. **Fix:** marks are saved per exam, must be between 0 and full marks, and the subject must be assigned to the student. An empty value removes the mark.
18. **Student validation was missing.**
    - A section from a different class was accepted.
    - A duplicate admission number caused a 500 error.
    - Auto student IDs (`last id + 1`) could collide with typed IDs.
    - Status, phone and dates were free text.

    **Fix:** all of these are validated, with clear messages.
19. **Payments.**
    - Receipt numbers used `count + 1`, so duplicates were possible.
    - Zero or negative amounts were accepted.
    - An unknown student caused a 500 error.

    **Fix:** receipt numbers come from the row ID and are unique; amounts are validated; the method is chosen from a list. Wrong payments can be voided, so the receipt numbers stay in order.
20. **Class and section problems.** Deleting a class left orphan fee plans, and sections could be created for classes that did not exist. Duplicate names differing only in case were allowed.
21. **Settings could be saved with an empty name** and a logo of any size.
22. **Creating a student login with a taken username crashed** (IntegrityError 500).
23. **Bad JSON** returned raw 500 or 422 errors that the UI could not show. **Fix:** clear validation messages (422) and a friendly error page or JSON.
24. **Deprecated APIs.** `datetime.utcnow()` and `Query.get()` were deprecated. Code was updated to SQLAlchemy 2.x style and timezone-aware times.

## Missing features promised in the README
25. **Subjects:** there was only an "add subject" box. **Added:**
    - full subject management (edit, delete, code, full marks, pass marks, credits, active);
    - default subjects per class, with "apply to students";
    - add or remove subjects per student;
    - a marks grid driven by the subject table;
    - grades, grade points, credit-weighted GPA and Pass/Fail/Incomplete status;
    - merit position;
    - two grading scales (Standard 4.00 and Bangladesh 5.00).
26. **Students as the main database:** the profile page now links everything to the student: details, subjects, marks per exam, result card, attendance, fees with dues and payments, and login.
27. **The fee due list and reminders did not exist.** **Added:**
    - a monthly fee per class;
    - dues calculated from the months since January (or the admission date);
    - a due list and SMS reminders;
    - fee month and fee type on each payment.
28. **The "Import Excel" button only showed an alert.** **Added:** real CSV import with row-by-row error report and a sample file; CSV export protected against formula injection; a printable student list.
29. **"Print Result Cards" only showed an alert.** **Added:** print a single card or all cards for a class and section, with logo, GPA, position, attendance and signature lines.
30. **No way to manage teachers or reset passwords.** **Added:** Staff accounts in Settings (add, reset, disable; the last admin cannot be disabled).
31. **No student portal.** A student login used to open the admin dashboard. **Added:** students see only their own profile, published results, attendance and fees.
32. **Exams could not be created from the UI.** **Added:** create, publish or unpublish, and delete exams. An exam that has marks cannot be deleted.

## User interface
33. **Not usable on phones:** a fixed 256 px sidebar and tables wider than the screen. **Fix:** collapsible mobile menu, responsive grids and scrollable tables (checked at 375 px).
34. **Needed internet; development-only CDN.** The app depended on the Tailwind Play CDN (not meant for production) and an unpinned `alpinejs@3.x.x`. **Fix:** prebuilt CSS and Alpine.js 3.17.5 are bundled, so the app works offline in schools with no internet.
35. **Errors were silent.** Failed requests showed nothing or "[object Object]", and an expired session broke the page. **Fix:** toast messages with the server's reason, and automatic redirect to login.
36. **Dead and broken code.**
    - The profile modal was never opened (`openProfile` was never called).
    - `x-cloak` had no CSS, so hidden elements flashed on load.
    - The SMS log used the date as the list key, so duplicate keys broke the list.
    - The fee amount was hard-coded to 1500.

    **Fix:** dead code removed, a proper `x-cloak` style added, unique keys used, and the fee amount is filled from the class fee.
37. **Edits could be lost.** Unsaved marks were lost when switching page, and marks typed while a save was running were dropped. **Fix:** unsaved-changes warning, and in-flight edits are kept.
38. **Guardian details were missing.** Relation, address, roll number and notes were not in the forms. **Fix:** they have been added.

## Documentation and packaging
39. **Wrong Windows commands.** HowToSetup used `python` on Windows; it now uses `py -m venv venv` and `py main.py`. It also claimed "no secrets hardcoded" while shipping fixed passwords. The docs were rewritten, including `.env` options, backup, upgrade, real SMS, and a forgotten-password procedure.
40. **No tests, linting or audit.** **Added:** a pytest suite (241 tests), ruff (clean) and pip-audit (clean).
