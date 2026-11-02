# VOVEOFRICA

Flask dating application designed for stateless container hosting. The application
uses PostgreSQL with PostGIS for proximity queries, Cloudflare R2 for profile
images, and Pusher Channels for real-time chat delivery.

## Local setup

1. Copy `.env.example` to `.env` and set `SECRET_KEY` and `DATABASE_URL` to a
   PostgreSQL connection. Use a PostGIS-enabled database and ensure the database
   role can activate the PostGIS extension.
2. Install dependencies and apply schema migrations:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m flask --app run.py db upgrade
   ```

3. Configure SMTP before enabling account registration and login, then start the
   app:

   ```powershell
   .\.venv\Scripts\python.exe run.py
   ```

The local server listens on port `7860`. `/health` performs a database probe and
returns HTTP 503 when the database is unavailable. Production requires a
32-character `SECRET_KEY`, SMTP settings, at least one `ADMIN_EMAILS` entry,
R2 credentials, and Pusher credentials. Production cookies are Secure and HSTS
is enabled behind the trusted proxy.

## PostgreSQL and PostGIS

The SQLAlchemy models use PostgreSQL-compatible types. The PostGIS migration
creates a `profiles` table with a nullable SRID 4326 point and a GiST geography
index. No existing MySQL records are copied by this schema migration. Back up
the source database and perform/verify a separate data transfer before changing
production `DATABASE_URL`; never run the schema-only upgrade against an empty
production database as a substitute for copying data.

Location is managed separately from the existing profile form:

- `PUT /api/matches/location` accepts a JSON body containing numeric `lat` and
  `lon` values. Coordinates are range-checked and stored as a PostGIS point.
- `GET /api/matches/feed?distance_meters=25000` returns nearby profile IDs,
  ordered by distance. The distance is in meters and is capped at 200,000.
- Both endpoints require the existing signed-in browser session. Browser writes
  remain subject to CSRF protection.

## Chat and media

Existing page URLs and server-side validation are retained. The chat page uses
authenticated Pusher private channels and stateless HTTP endpoints under
`/api/chat`: `/pusher/auth`, `/send`, `/typing`, and `/read`. Message length,
profanity, match/block authorization, persistence, unread notifications, and
the 30-message-per-minute limit remain enforced.

R2 uploads are private and profile images continue to be served through the
authenticated profile-photo route. JPG, PNG, and WebP uploads are validated,
EXIF metadata is stripped, and images are resized and stored as WebP. Local
disk remains available for development if R2 is not configured. Existing S3
photo references remain readable when their legacy bucket is configured.

## Container

Hugging Face Spaces can build the included Dockerfile directly. The container
serves Gunicorn on port `7860`; secrets must be configured in the hosting
environment and must not be copied into the image.

To build locally:

```powershell
docker build -t voveofrica .
docker run --env-file .env -p 7860:7860 voveofrica
```

Database migrations are a controlled release step and are not run at container
startup. Back up production data and apply migrations only after validating the
target PostgreSQL/PostGIS database.

## Account, safety, and payments

New accounts verify email with a six-digit code before access is granted.
Password logins also require an email code. Codes expire after 10 minutes,
are single-use, allow five attempts, and can be requested once per minute.
Configure outbound SMTP before enabling sign-in.

The Free community tier includes profile creation, discovery, matching, chat,
safety controls, and up to 10 likes per UTC day. Premium raises the daily like
limit to 50. The optional 24-hour Boost is separate. Paystack checkout remains
disabled until `PAYSTACK_SECRET_KEY` and a valid HTTPS
`PAYSTACK_CALLBACK_URL` are configured. Purchases are verified server-side and
do not auto-renew.

## Tests

The test suite uses SQLite for isolated HTTP tests. The GitHub Actions workflow
uses PostgreSQL with PostGIS and runs the Alembic upgrade before the tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
