# City Care Hospital Management System (HMS)

Flask + PostgreSQL (Neon) hospital management system.
**The database starts completely empty** - no demo doctors, patients, medicines or users.
Everything is entered by you through the app.

## 1. Configure the database (`.env`)

The `.env` file in the project root holds the connection:

```env
DATA_BASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require&channel_binding=require
SECRET_KEY=<long random string>
FLASK_DEBUG=0
```

`.env.example` is a template. **Never commit `.env`** (it is already in `.gitignore`).

## 2. Run

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py                       # http://127.0.0.1:5000
```

Production: `gunicorn -w 3 run:app`

On every start the app connects to PostgreSQL and **creates any missing tables (empty)**.
Existing tables and data are never touched or reset.

## 3. First-time flow

1. Open the site -> you are redirected to **/setup** (only this page works until an admin exists).
2. Create the **Administrator** account (name, username, email, password >= 8 chars). `/setup` is then permanently disabled.
3. You land on **Setup & Master Data** (sidebar -> *Setup & Master Data*) with a checklist:
   1. Departments  2. Doctors (creates the doctor's login too)  3. Wards (can auto-create beds)  4. Beds
   5. Lab tests  6. Radiology tests  7. Medicines (+ Suppliers)  8. Staff  - plus Inventory items
4. Create other users from *Administration -> Create User* (or while adding doctors / staff).

Add / Manage buttons also appear on the Doctors, Departments, Beds, Pharmacy, Lab, Radiology, Inventory and Staff pages.

| Master data | Who can manage |
|---|---|
| Departments, Doctors, Staff, Wards, Beds | Admin |
| Medicines, Suppliers | Admin, Pharmacist |
| Lab tests | Admin, Lab technician |
| Radiology tests | Admin, Radiologist |
| Inventory items | Admin, Nurse |

## 4. What changed vs. the original project

* SQLite -> **PostgreSQL** (`psycopg2`), connection pooling tuned for Neon (`pool_pre_ping`, recycle).
* **All seed / demo data removed** (`seed.py` deleted, SQLite file removed).
* Empty tables auto-created at startup (advisory-lock protected, retries while Neon wakes up).
* **First-run admin setup** page; no default passwords anywhere.
* New master-data screens (add / edit / activate / delete where safe) with duplicate checks and audit log.
* CSRF protection on every form, safe `next=` redirect, deactivated users are logged out, change-password page, admin edit/reset-password for users.
* Staff attendance can now be marked (admin).
* DB indexes on frequently queried columns; circular FK (`departments` <-> `doctors`) handled for PostgreSQL.

## 5. Project structure

```
hms_flask/
|-- run.py  config.py  requirements.txt  .env  .env.example  Procfile
`-- app/
    |-- __init__.py            # factory: DB init, setup gate, CSRF, error pages
    |-- models.py
    |-- utils/db_init.py       # creates missing tables
    |-- utils/decorators.py
    |-- blueprints/            # auth, masters (setup screens), patients, billing, adt, ...
    `-- templates/ static/
```

## 6. Security notes

* Rotate the database password if it was ever shared in chat/email (Neon console -> Roles -> Reset password) and update `.env`.
* Use a strong unique `SECRET_KEY` in production and serve over HTTPS.
