import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
SUBREDDITS   = ["wallstreetbets", "DeepFuckingValue"]
POST_LIMIT   = 3          # top N hot posts per subreddit
FETCH_COUNT  = 15         # fetch more so we can skip already-sent ones
STATE_FILE   = "sent_posts.json"
MAX_HISTORY  = 500        # cap state file size

TELEGRAM_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]   # e.g. @yourchannel or -100xxxxxxxxxx
# ─────────────────────────────────────────────────────────────────────────────


def load_sent() -> set:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()


def save_sent(sent: set):
    # Keep only the most recent MAX_HISTORY IDs to avoid unbounded growth
    trimmed = list(sent)[-MAX_HISTORY:]
    with open(STATE_FILE, "w") as f:
        json.dump(trimmed, f)


def fetch_hot(subreddit: str) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={FETCH_COUNT}"
    req = urllib.request.Request(url, headers={"User-Agent": "reddit-telegram-bot/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [p["data"] for p in data["data"]["children"] if not p["data"].get("stickied")]


def format_message(post: dict, subreddit: str) -> str:
    title   = post["title"]
    score   = f"{post['score']:,}"
    comments = f"{post['num_comments']:,}"
    url     = f"https://reddit.com{post['permalink']}"
    flair   = post.get("link_flair_text") or ""
    flair_str = f"  [{flair}]" if flair else ""

    # Include direct link if it's not a self-post
    content_url = ""
    if not post.get("is_self") and post.get("url"):
        content_url = f"\n🔗 <a href=\"{post['url']}\">Link</a>"

    return (
        f"🔥 <b>r/{subreddit}</b>{flair_str}\n"
        f"{title}\n\n"
        f"⬆️ {score} upvotes  💬 {comments} comments"
        f"{content_url}\n"
        f"👉 <a href=\"{url}\">View on Reddit</a>"
    )


def send_telegram(message: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main():
    sent  = load_sent()
    newly_sent = set()

    for subreddit in SUBREDDITS:
        print(f"\n── r/{subreddit} ──")
        try:
            posts = fetch_hot(subreddit)
        except Exception as e:
            print(f"  ERROR fetching: {e}")
            continue

        pushed = 0
        for post in posts:
            if pushed >= POST_LIMIT:
                break
            pid = post["id"]
            if pid in sent:
                print(f"  skip (already sent): {pid}")
                continue

            msg = format_message(post, subreddit)
            try:
                send_telegram(msg)
                print(f"  ✓ sent [{pid}]: {post['title'][:60]}")
                newly_sent.add(pid)
                pushed += 1
                time.sleep(0.5)   # be polite to Telegram rate limits
            except Exception as e:
                print(f"  ERROR sending {pid}: {e}")

        if pushed == 0:
            print("  No new posts to send.")

    sent.update(newly_sent)
    save_sent(sent)
    print(f"\nDone. {len(newly_sent)} post(s) sent. State saved.")


if __name__ == "__main__":
    main()
