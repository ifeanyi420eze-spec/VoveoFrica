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

3. Install dependencies and apply database migrations:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m flask --app run.py db upgrade
   ```

4. Start the application:

   ```powershell
   .\.venv\Scripts\python.exe run.py
   ```

Set `FLASK_DEBUG=1` in `.env` only when you intentionally want local development debug mode.

Subscription plan descriptions and prices are stored in the MySQL `subscription_plan` table. Homepage counts, profiles, matches, and conversations are read from application data rather than demo values embedded in templates.
