"""A simple limit on recipe requests, so one person cannot use up the whole Gemini quota.

Each person is their account when signed in, or their address when not. We keep the
times of their requests in the last hour, in memory. Restarting the app clears the
counts, which is fine for one server.
"""

import time

from fastapi import HTTPException

from app.core.config import get_settings

WINDOW_SECONDS = 60 * 60

recent = {}   # who -> times of their requests in the last hour


def who_is_asking(request, user):
    if user is not None:
        return f"user:{user.id}"
    return f"address:{request.client.host if request.client else 'unknown'}"


def check_recipe_limit(request, user):
    """Count this request, or refuse it with 429 when the hourly limit is reached."""
    limit = get_settings().recipe_requests_per_hour
    if limit == 0:
        return
    who = who_is_asking(request, user)
    now = time.time()
    times = [t for t in recent.get(who, []) if now - t < WINDOW_SECONDS]
    if len(times) >= limit:
        recent[who] = times
        minutes = int((WINDOW_SECONDS - (now - times[0])) // 60) + 1
        raise HTTPException(
            status_code=429,
            detail=f"You have asked for {limit} recipes in the last hour. "
                   f"Please try again in {minutes} minutes.",
            headers={"Retry-After": str(minutes * 60)},
        )
    times.append(now)
    recent[who] = times
