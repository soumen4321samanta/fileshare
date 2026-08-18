# FileShare — Simple Upload Page + Admin Dashboard

A tiny Django app with two pages:

- **`/`** — public upload page. Anyone with the link can select/drag files and upload them. No login needed.
- **`/admin/`** — password-protected dashboard (Django's built-in admin) listing every uploaded file with a download link.

---

## 1. Run it locally (optional, to try before deploying)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser   # sets your admin username/password
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` for the upload page and `http://127.0.0.1:8000/admin/` for the dashboard.

---

## 2. Deploy to Render.com (free)

1. Push this project to a **GitHub repo** (Render deploys from Git).
2. Go to [render.com](https://render.com) → **New +** → **Blueprint**, and point it at your repo. Render will read `render.yaml` in this project and set everything up automatically (build command, start command, and a random `SECRET_KEY`).
   - If you'd rather set it up manually instead of using the Blueprint: **New +** → **Web Service** → connect your repo → Build Command: `./build.sh` → Start Command: `gunicorn fileshare.wsgi:application`.
3. Once it's deployed, open the **Shell** tab for your service on Render and run:
   ```bash
   python manage.py createsuperuser
   ```
   This creates your admin login (username + password) — do this once.
4. Your site is live at `https://<your-app-name>.onrender.com`
   - Share `https://<your-app-name>.onrender.com/` with whoever needs to send you files.
   - You check uploads at `https://<your-app-name>.onrender.com/admin/`.

---

## ⚠️ Important: free-tier storage is not permanent

Render's **free** web service plan uses a temporary filesystem — it resets whenever the service redeploys, restarts, or spins down after inactivity. That means:

- Uploaded files **and** the small database that lists them can disappear after some time.
- This is fine if you check the admin dashboard and download files soon after they're sent.
- It is **not** reliable for long-term storage.

**If you need uploads to survive restarts**, pick one:

- **Render Persistent Disk** (~$1/mo for 1GB) — attach a disk to the service in Render's dashboard, and point `MEDIA_ROOT` in `settings.py` at that disk's mount path. Simplest fix, small cost.
- **Free cloud storage instead of local disk** — e.g. Cloudinary's free tier. This needs `django-storages` + `cloudinary` packages and a few settings changes. Ask if you'd like this version instead — it stays 100% free and is more durable than a persistent disk trick.

---

## Notes

- Max upload size is 25MB per file by default — change `MAX_UPLOAD_SIZE` in `fileshare/settings.py` if you need more.
- Multiple files can be selected/dropped at once on the upload page.
- File names are stored uniquely (a random ID is added) so two different people uploading `photo.jpg` never overwrite each other; the original name is still shown in the dashboard.
- The admin dashboard is Django's built-in admin — one added benefit is you can also search uploaded filenames from there.
