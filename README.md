# VOVEOFRICA

## Local setup

1. If you do not already have a local environment file, create one from the example:

   ```powershell
   if (!(Test-Path .env)) { Copy-Item .env.example .env }
   ```

2. Edit `.env` and set `DATABASE_URL` to the MySQL connection for your XAMPP database and `SECRET_KEY` to a random value. Generate a key with:

   ```powershell
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
   ```

   Do not commit `.env`.

3. Configure outbound SMTP as described below before enabling the updated login flow, then install dependencies and apply database migrations:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m flask --app run.py db upgrade
   ```

4. Start the application:

   ```powershell
   .\.venv\Scripts\python.exe run.py
   ```

Run the local health check after startup:

```powershell
Invoke-WebRequest http://127.0.0.1:5000/health | Select-Object StatusCode, Content
```

The endpoint performs a database probe and returns HTTP 503 when the database
is unavailable. It never returns credentials or other secret configuration.

Set `FLASK_DEBUG=1` in `.env` only when you intentionally want local development debug mode. For production, set `APP_ENV=production` and keep `FLASK_DEBUG=0`; production mode requires a 32-character or longer `SECRET_KEY`, secure session cookies, trusted HTTPS proxy headers, and HSTS.

## Production traffic, limits, and live chat

The application is safe to run behind an HTTPS load balancer, but the proxy must
forward `Upgrade` and `Connection` headers for the `/socket.io` path and use
sticky sessions. Run one Gunicorn process per Elastic Beanstalk instance as
configured in the root `Procfile`; do not add workers without a shared Socket.IO
message queue.

Set `REDIS_URL` in every application instance. It is used for cross-instance
Socket.IO broadcasts and, by default, for the distributed Flask-Limiter store.
Without Redis, chat works only while all connected users are on the same
application process, and the default in-memory limiter is local to one process.
Set `RATELIMIT_STORAGE_URI` explicitly if the limiter should use a different
Redis database. Restrict `SOCKETIO_CORS_ALLOWED_ORIGINS` to the exact HTTPS
origins serving the application; leave it empty to keep Socket.IO same-origin
only.

Sessions use an HttpOnly, SameSite=Lax cookie; production sets `Secure` so the
cookie is sent only over HTTPS. Do not embed authentication tokens in URLs or
client-side storage. CSRF protection remains enabled for browser form requests.

Email OTPs are six digits, expire after 10 minutes, are single-use, allow five
attempts, and can be requested only once per minute per account. Login,
registration, verification, and resend endpoints also have IP-based rate
limits. SMTP delivery is synchronous today; for high volume, move email
delivery to a durable worker queue rather than increasing request timeouts.

The application does not currently cache database pages. Add Redis-backed
response/data caching only after measuring a slow query, and invalidate cached
counts and plans whenever the underlying records change. Do not cache private
profile, notification, or chat responses.

## AWS Elastic Beanstalk deployment

The root `Procfile` runs Flask-SocketIO through Gunicorn's threaded worker with one process per instance, as required for the current Socket.IO deployment. Start with one Elastic Beanstalk instance. Scaling to multiple instances requires both load-balancer sticky sessions and a shared Socket.IO message queue (for example Redis); otherwise chat events and rooms are not shared across instances. Do not increase the Gunicorn worker count without adding a shared Socket.IO message queue.

The GitHub Actions workflow `.github/workflows/deploy-elastic-beanstalk.yml` deploys commits pushed to `main` to an Elastic Beanstalk environment. Configure a GitHub repository **Environment** named `production`, add branch/deployment approval protection, and define these environment variables (not secrets):

```text
APP_ENV=production
AWS_ROLE_ARN
AWS_REGION
EB_APPLICATION_NAME
EB_ENVIRONMENT_NAME
EB_DEPLOYMENT_BUCKET
ADMIN_EMAILS
PROFILE_PHOTO_S3_BUCKET
```

Configure GitHub-to-AWS authentication with OIDC. Restrict the IAM role trust policy's `token.actions.githubusercontent.com:sub` to this repository's `production` environment and audience `sts.amazonaws.com`; use the exact subject claim format shown by GitHub for this repository (newer repositories may include immutable owner/repository IDs). Grant the role only `s3:PutObject` and `s3:GetObject` on the deployment-bucket bundle prefix, plus the required Elastic Beanstalk create-version, update-environment, and describe/wait permissions. Do not create long-lived AWS access keys for GitHub Actions.

Store application credentials in AWS Secrets Manager and configure the Elastic Beanstalk environment to inject them as environment variables. Set `SECRET_KEY`, `DATABASE_URL`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM_EMAIL` from Secrets Manager. Set non-secret runtime values such as `APP_ENV=production`, `FLASK_DEBUG=0`, `SMTP_HOST=smtp-relay.brevo.com`, `SMTP_PORT=587`, `SMTP_USE_TLS=true`, and `ADMIN_EMAILS` in Elastic Beanstalk configuration. If payments are enabled, also configure `PAYSTACK_SECRET_KEY` from Secrets Manager and set `PAYSTACK_CALLBACK_URL` to the real HTTPS callback. These production values must not be added to GitHub workflow files, committed `.env` files, or deployment bundles.

For durable member photos, create a private S3 bucket and set `PROFILE_PHOTO_S3_BUCKET` and `AWS_REGION` in the Elastic Beanstalk environment. Production startup fails unless these values, working SMTP settings, and at least one `ADMIN_EMAILS` value are configured. Grant the **Elastic Beanstalk EC2 instance profile** only the required `s3:PutObject`, `s3:GetObject`, and `s3:DeleteObject` permissions for that bucket's `profile-photos/*` prefix. Do not make the bucket public; profile images are served through the app's authenticated route. Existing local-disk photo files are not copied automatically—before switching an existing database to S3 storage, upload each file to `profile-photos/<filename>` and update its user's `profile_photo` value to `s3:profile-photos/<filename>`.

The workflow deploys application code only; it does not apply database migrations automatically. Back up the production database, verify SMTP and environment settings, and run migrations as a controlled release step before enabling code that depends on a new schema. For the current pending email verification migration, run `flask --app run.py db upgrade` in the production environment only after outbound SMTP delivery has been tested. The workflow validates the production environment marker, admin email list, and profile-photo bucket before packaging. It also checks that the Alembic migration graph has a valid head. It does not apply migrations automatically. Back up the production database, deploy the application only after the migration check passes, and run the migration as a controlled release step:

```powershell
python -m flask --app run.py db upgrade
```

Run that command from a secured release workstation with the production `DATABASE_URL` and `APP_ENV=production` loaded, then verify the application health endpoint and log output. Do not put database credentials in GitHub variables or commit `.env`.

## Email verification and sign-in security

New accounts must verify their email address with a six-digit code before access is granted. Each password login also requires a one-time code sent to the account email. Codes expire after 10 minutes, are single-use, allow up to five attempts, and can be requested once per minute. Existing accounts are retained as email-verified when the migration runs.

Configure outbound mail in `.env` before enabling registration or login:

```text
SMTP_HOST=smtp.your-provider.example
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=VOVEOFRICA <no-reply@your-domain.example>
SMTP_USE_TLS=true
```

Use the SMTP credentials and sender address supplied by your email provider. Keep credentials private and do not commit `.env`. Email verification and sign-in cannot complete until SMTP is configured and reachable.

The repository includes regression tests for the OTP sender and health check.
Install dependencies and run them with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Discovery results are intentionally capped at 100 profiles per request. Add
cursor pagination before increasing that limit; loading the entire member
directory into one response will degrade database and browser performance.

Subscription plan descriptions and prices are stored in the MySQL `subscription_plan` table. Homepage counts, profiles, matches, and conversations are read from application data rather than demo values embedded in templates.

After updating the app, configure SMTP and apply migrations with `.\.venv\Scripts\python.exe -m flask --app run.py db upgrade` before enabling the updated registration and login flow or using profile preferences, notifications, and blocking controls. Do not deploy the mandatory email-code login without a working outbound email service; authentication intentionally fails closed if email delivery is unavailable. Members can save location, relationship-goal, and interest preferences for discovery; profile photos accept JPG, PNG, and WebP files up to 5 MB and are stored under the local `instance\profile_photos` folder rather than in the public static directory. Verification is manually reviewed by an administrator after the member contacts support; do not approve a badge until the review is complete. The app does not collect identity documents.

## Membership and Paystack

The Free community tier includes profile creation, discovery, matching, match messaging, safety controls, and up to 10 likes per UTC day. Database-managed Premium plans are one-time, non-renewing passes; Premium raises the daily like limit to 50 and enables saved discovery preferences and the received-likes list. The optional 24-hour profile Boost is a separate one-time purchase that prioritizes a profile in discovery; it does not guarantee engagement and does not require Premium.

To enable live Paystack checkout, set `PAYSTACK_SECRET_KEY` to the secret key for the intended Paystack environment and `PAYSTACK_CALLBACK_URL` to the public HTTPS callback URL for this deployment, exactly `/payments/paystack/callback`. Configure the Paystack dashboard webhook to send events to `https://<your-domain>/payments/paystack/webhook`. Keep secret keys out of source control and logs. Checkout remains unavailable unless both the secret key and a valid HTTPS callback URL are configured. The app initializes purchases in NGN and activates entitlements only after server-side Paystack transaction verification; webhook signatures are checked before processing. Test with Paystack test credentials before enabling live charges.

Plan prices, durations, and active flags are stored in the `subscription_plan` table and can be adjusted there. The migration seeds the optional one-day Boost at ₦500; review that price and the existing plan ladder against payment costs and observed renewal/conversion data before launch. The annual plan's displayed monthly equivalent is based on twelve months. Purchases do not auto-renew; Premium time bought while another Premium pass is active is scheduled to begin after the current pass expires.
