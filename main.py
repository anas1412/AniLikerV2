import os
import queue
import threading
import time
from contextlib import asynccontextmanager
from os.path import dirname, join
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from utils import oauth

dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

CLIENT_ID = os.environ.get("ANILIST_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("ANILIST_CLIENT_SECRET", "")
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
REDIRECT_URI = f"{BASE_URL}/api/auth/callback"

# In-memory session store: session_id -> {token, username}
sessions: dict[str, dict] = {}
# Per-session SSE queues: session_id -> queue.Queue
sse_queues: dict[str, queue.Queue] = {}

# Job state
active_jobs: dict[str, dict] = {}


def generate_session_id() -> str:
    import secrets
    return secrets.token_urlsafe(32)


def get_session_token(session_id: str) -> Optional[str]:
    s = sessions.get(session_id)
    if s:
        return s.get("token")
    return None


def get_session_user(session_id: str) -> Optional[str]:
    s = sessions.get(session_id)
    if s:
        return s.get("username")
    return None


def get_or_create_queue(session_id: str) -> queue.Queue:
    if session_id not in sse_queues:
        sse_queues[session_id] = queue.Queue()
    return sse_queues[session_id]


def run_query(token: str, query: str, variables: dict, retries: int = 3) -> dict:
    for attempt in range(retries):
        response = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": variables},
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {token}",
            },
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()["data"]
        elif response.status_code == 429:
            reset = response.headers.get("X-RateLimit-Reset")
            wait = 60
            if reset:
                try:
                    wait = max(int(reset) - int(time.time()), 10)
                    wait = min(wait, 120)
                except (ValueError, TypeError):
                    pass
            time.sleep(wait)
        else:
            raise Exception(f"AniList query failed (HTTP {response.status_code}): {response.text[:200]}")
    raise Exception("AniList query failed after retries")


def get_user_id(token: str, username: str) -> int:
    query = """
        query ($username: String) {
          User (name: $username) {
            id
          }
        }
    """
    data = run_query(token, query, {"username": username})
    user = data.get("User")
    if not user or not user.get("id"):
        raise Exception(f"User '{username}' not found")
    return user["id"]


def fetch_activities(token: str, user_id: int, page: int, activity_types: list[str]) -> dict:
    query = """
        query ($user_id: Int, $page: Int, $perPage: Int, $q_options: [ActivityType]) {
          Page (page: $page, perPage: $perPage) {
            pageInfo {
              hasNextPage
            }
            activities (userId: $user_id, sort: ID_DESC, type_in: $q_options) {
              ... on ListActivity {
                id
                isLiked
                status
                media {
                  title { userPreferred }
                  type
                }
              }
              ... on TextActivity {
                id
                isLiked
                text
              }
              ... on MessageActivity {
                id
                isLiked
                message
              }
            }
          }
        }
    """
    variables = {
        "user_id": user_id,
        "page": page,
        "perPage": 30,
        "q_options": activity_types,
    }
    return run_query(token, query, variables)["Page"]


def toggle_like(token: str, activity_id: int):
    query = """
        mutation ($id: Int) {
          ToggleLikeV2(id: $id, type: ACTIVITY) {
            __typename
          }
        }
    """
    run_query(token, query, {"id": activity_id})


def activity_detail(activity: dict) -> str:
    if "status" in activity:
        media_type = activity.get("media", {}).get("type", "")
        title = activity.get("media", {}).get("title", {}).get("userPreferred", "Unknown")
        return f"{media_type}: {title} ({activity['status']})"
    elif "text" in activity:
        text = activity["text"][:80]
        return f"Text: \"{text}\""
    elif "message" in activity:
        msg = activity["message"][:80]
        return f"Message: \"{msg}\""
    return f"Activity #{activity['id']}"


def like_worker(session_id: str, username: str, activity_types: list[str]):
    """Background thread that likes all activities for a user."""
    q = get_or_create_queue(session_id)
    token = get_session_token(session_id)

    if not token:
        q.put({"event": "error_msg", "data": {"message": "No auth token. Please login again."}})
        q.put({"event": "status", "data": {"message": "Done"}})
        return

    try:
        user_id = get_user_id(token, username)
        q.put({"event": "status", "data": {"message": f"Found user (ID: {user_id})"}})
    except Exception as e:
        q.put({"event": "error_msg", "data": {"message": str(e)}})
        q.put({"event": "status", "data": {"message": "Done"}})
        return

    page = 1
    while True:
        try:
            page_data = fetch_activities(token, user_id, page, activity_types)
        except Exception as e:
            q.put({"event": "error_msg", "data": {"message": f"Failed to fetch page {page}: {e}"}})
            q.put({"event": "status", "data": {"message": "Done"}})
            return

        activities = page_data.get("activities", [])
        has_next = page_data.get("pageInfo", {}).get("hasNextPage", False)

        for activity in activities:
            if activity.get("isLiked"):
                continue
            try:
                toggle_like(token, activity["id"])
                detail = activity_detail(activity)
                q.put({"event": "activity_liked", "data": {"id": activity["id"], "detail": detail}})
            except Exception as e:
                q.put({"event": "error_msg", "data": {"message": f"Failed to like #{activity['id']}: {e}"}})

        if not has_next:
            q.put({"event": "status", "data": {"message": "Done"}})
            break

        q.put({"event": "page_complete", "data": {"page": page, "remaining": 60}})
        page += 1
        time.sleep(60)

    active_jobs.pop(session_id, None)


# --- FastAPI App ---

app = FastAPI(title="AniLiker", docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = join(dirname(__file__), "static", "index.html")
    with open(html_path, "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/auth/status")
async def auth_status(request: Request):
    sid = request.cookies.get("session_id")
    if sid and sid in sessions:
        return {"authenticated": True, "username": sessions[sid].get("username", "")}
    return {"authenticated": False}


@app.get("/api/auth/login")
async def auth_login():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="AniList API credentials not configured on the server.")
    authorization_url, state = oauth.get_authorization_url(CLIENT_ID, REDIRECT_URI)
    return RedirectResponse(url=authorization_url)


@app.get("/api/auth/callback")
async def auth_callback(request: Request):
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error or not code:
        return RedirectResponse(url="/?auth=failed")

    try:
        token_data = oauth.fetch_token(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, str(request.url))
    except Exception:
        return RedirectResponse(url="/?auth=failed")

    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(url="/?auth=failed")

    # Fetch the authenticated user's name
    try:
        me_query = """
            query { Viewer { id name } }
        """
        resp = requests.post(
            "https://graphql.anilist.co",
            json={"query": me_query},
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {access_token}",
            },
            timeout=10,
        )
        username = resp.json()["data"]["Viewer"]["name"]
    except Exception:
        username = "unknown"

    session_id = generate_session_id()
    sessions[session_id] = {"token": access_token, "username": username}

    response = RedirectResponse(url="/?auth=success")
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
    )
    return response


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    sid = request.cookies.get("session_id")
    if sid:
        sessions.pop(sid, None)
        sse_queues.pop(sid, None)
        active_jobs.pop(sid, None)
    response = RedirectResponse(url="/")
    response.delete_cookie("session_id")
    return response


class LikeRequest(BaseModel):
    username: str
    activity_types: list[str] = ["TEXT", "ANIME_LIST", "MANGA_LIST", "MESSAGE"]


@app.post("/api/like")
async def start_liking(req: LikeRequest, request: Request):
    sid = request.cookies.get("session_id")
    if not sid or sid not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated. Please login with AniList first.")

    if sid in active_jobs:
        raise HTTPException(status_code=409, detail="A liking job is already running.")

    valid_types = {"TEXT", "ANIME_LIST", "MANGA_LIST", "MESSAGE"}
    types = [t for t in req.activity_types if t in valid_types]
    if not types:
        raise HTTPException(status_code=400, detail="No valid activity types selected.")

    if not req.username.strip():
        raise HTTPException(status_code=400, detail="Username is required.")

    active_jobs[sid] = {"username": req.username, "running": True}

    t = threading.Thread(
        target=like_worker,
        args=(sid, req.username.strip(), types),
        daemon=True,
    )
    t.start()

    return {"status": "started", "username": req.username}


@app.get("/api/status")
async def sse_status(request: Request):
    sid = request.cookies.get("session_id")
    if not sid:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    q = get_or_create_queue(sid)

    async def event_generator():
        import asyncio
        while True:
            if await request.is_disconnected():
                break
            try:
                item = q.get_nowait()
                yield f"event: {item['event']}\ndata: {__import__('json').dumps(item['data'])}\n\n"
            except queue.Empty:
                await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
