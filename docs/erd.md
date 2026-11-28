# Madrasa Pro — Entity relationship diagram

```mermaid
erDiagram
    users ||--o{ teacher_subjects : "teaches"
    users ||--o{ routine_slots : "assigned"
    users ||--o| students : "student login"
    classes ||--o{ sections : has
    classes ||--o{ students : contains
    classes ||--o{ class_subjects : defaults
    classes ||--o{ fee_plans : priced
    sections ||--o{ students : groups
    sections ||--o{ routine_slots : timetable
    subjects ||--o{ class_subjects : offered
    subjects ||--o{ student_subjects : enrolled
    subjects ||--o{ marks : scored
    subjects ||--o{ teacher_subjects : taught
    subjects ||--o{ routine_slots : scheduled
    students ||--o{ student_subjects : takes
    students ||--o{ marks : receives
    students ||--o{ attendance : recorded
    students ||--o{ payments : pays
    exams ||--o{ marks : includes
    periods ||--o{ routine_slots : timeslot
    academic_years ||--o{ exams : holds
    school_settings ||--|| school_settings : "single row"
```

## Tables

| Table | Purpose |
|-------|---------|
| users | Admin, teacher and student accounts |
| school_settings | Institution name, logo, currency, working days |
| classes / sections | Academic structure |
| students | Student records |
| subjects / class_subjects / student_subjects | Curriculum |
| exams / marks | Results |
| attendance | Daily attendance |
| fee_plans / payments | Fees and receipts |
| periods / teacher_subjects / routine_slots | Timetable |
| academic_years | Year label for exams |
| login_attempts | 1.0.4: failed logins for the persistent login throttle (no FK) |
| app_settings | 1.0.5: SMTP / payment gateway / SMS settings, one row per field; secrets Fernet-encrypted (no FK) |
| currencies | 1.0.5: currencies with symbol, rate, decimals; one default (no FK) |
| languages / translations | 1.0.5: interface languages and the admin's own texts (translations.language_code -> languages.code) |
| schema_migrations | Numbered migrations applied (app/database.py) |

Every foreign key is indexed and declares ON DELETE (CASCADE / RESTRICT / SET NULL); the full list is at the top of
`database/schema.sql`. Payments, exams with marks and classes with students are protected by RESTRICT and by explicit
checks in the API.
