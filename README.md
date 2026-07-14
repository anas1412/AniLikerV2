# AniLikerV2

A web-based tool that bulk-likes activity posts on any AniList profile.

## Quick Start (Local)

### 1. Create an AniList API Client

1. Go to **https://anilist.co/settings/developer**
2. Click **Create New Client**
3. Fill in:
   - **Name:** anything (e.g. "AniLiker")
   - **Redirect URL:** `http://127.0.0.1:8080/api/auth/callback`
4. Click **Save**
5. Copy the **Client ID** and **Client Secret** you see on the next page

### 2. Set up the project

Open a terminal in this folder and run:

```bash
cp .env.example .env
```

Then edit `.env` and paste your credentials:

```
ANILIST_CLIENT_ID=paste_here
ANILIST_CLIENT_SECRET=paste_here
BASE_URL=http://127.0.0.1:8080
```

### 3. Install and run

```bash
pip install -r requirements.txt
python main.py
```

Then open **http://127.0.0.1:8080** in your browser.

### 4. Use it

1. Click **"Login with AniList"** in the top right
2. Authorize the app on AniList
3. You'll be redirected back to the app, now logged in
4. Type any AniList username
5. Pick which activity types to like (Text, Anime, Manga, Messages)
6. Click **Start**

The log shows each activity being liked in real time. It pauses 60 seconds between pages to avoid hitting AniList's rate limit.

---

## Deploy to Replit

1. Import this repo into Replit
2. Go to the **Secrets** tab (lock icon in the left sidebar) and add:
   - `ANILIST_CLIENT_ID` — your Client ID from step 1
   - `ANILIST_CLIENT_SECRET` — your Client Secret from step 1
   - `BASE_URL` — your Replit URL, e.g. `https://my-project.myusername.repl.co`
3. Go back to **https://anilist.co/settings/developer**, edit your API client, and change the **Redirect URL** to:
   ```
   https://my-project.myusername.repl.co/api/auth/callback
   ```
4. Click **Run**

---

## Troubleshooting

**"ModuleNotFoundError: No module named 'requests'"**
Run `pip install -r requirements.txt` to install dependencies.

**Login doesn't work / callback error**
Make sure the Redirect URL in your AniList API client settings exactly matches:
- For local: `http://127.0.0.1:8080/api/auth/callback`
- For Replit: `https://your-project.repl.co/api/auth/callback`

**"AniList API credentials not configured"**
Your `.env` file is missing or empty. Make sure you filled in `ANILIST_CLIENT_ID` and `ANILIST_CLIENT_SECRET`.

---

## License

BSD 3-Clause — see [LICENSE](LICENSE).
