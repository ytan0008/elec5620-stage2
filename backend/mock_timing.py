"""IELTS mock timing, as on test day.

The written test (Listening -> Reading -> Writing) runs in order and each section
has its own clock: when a section's time is up, or the learner finishes it early,
it closes and the next one starts. Time does not carry over and a closed section
cannot be reopened. The speaking test is a separate session that can be taken
before or after the written test, but it must be finished the same day.

The state lives in MockExam.sections["timing"]. Every function returns a new
dict so SQLAlchemy notices the change to the JSON column.
"""
from datetime import datetime, timedelta, timezone

WRITTEN = ("listening", "reading", "writing")
SAVE_GRACE = timedelta(seconds=60)  # autosave that was in flight when the clock hit zero still counts


def _at(value: str | None) -> datetime | None:
    if not value:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def new_timing(exam: str, now: datetime, tz_offset_minutes: int | None) -> dict | None:
    """IELTS only. The day ends at 23:59:59 in the learner's own time zone (offset east of UTC, in minutes)."""
    if exam != "IELTS":
        return None
    offset = timedelta(minutes=tz_offset_minutes or 0)
    local_end = (now + offset).replace(hour=23, minute=59, second=59, microsecond=0)
    return {"mode": "ielts", "current": None, "current_started": None, "closed": [], "written_started": None, "day_deadline": (local_end - offset).isoformat()}


def is_timed(sections: dict) -> bool:
    return (sections.get("timing") or {}).get("mode") == "ielts"


def section_deadline(sections: dict, timing: dict) -> datetime | None:
    if not timing.get("current"):
        return None
    return _at(timing["current_started"]) + timedelta(seconds=sections[timing["current"]].get("duration_seconds", 0))


def written_done(timing: dict) -> bool:
    return all(skill in timing.get("closed", []) for skill in WRITTEN)


def written_running(timing: dict) -> bool:
    return bool(timing.get("current"))


def day_over(timing: dict, now: datetime) -> bool:
    return now > _at(timing["day_deadline"])


def _close_current(timing: dict, at: datetime) -> dict:
    """Close the running section and start the next one at `at` (or finish the written test)."""
    current = timing["current"]
    closed = [*timing["closed"], current]
    following = [skill for skill in WRITTEN if skill not in closed]
    return {**timing, "closed": closed, "closed_at": {**timing.get("closed_at", {}), current: at.isoformat()},
            "current": following[0] if following else None, "current_started": at.isoformat() if following else None}


def start_written(timing: dict, now: datetime) -> dict:
    return {**timing, "current": WRITTEN[0], "current_started": now.isoformat(), "written_started": now.isoformat()}


def finish_current(timing: dict, now: datetime) -> dict:
    """The learner ends the running section early and moves on."""
    return _close_current(timing, now) if timing.get("current") else timing


def advance(sections: dict, now: datetime) -> dict:
    """Close every section whose time is up. The next section starts when the previous one ended, so
    a learner who was away finds the clock where it would be on test day."""
    timing = sections["timing"]
    while timing.get("current"):
        deadline = section_deadline(sections, timing)
        if now < deadline:
            break
        timing = _close_current(timing, deadline)
    return timing


def close_all(timing: dict, now: datetime) -> dict:
    while timing.get("current"):
        timing = _close_current(timing, now)
    return timing


def can_edit(sections: dict, skill: str, now: datetime) -> bool:
    timing = sections["timing"]
    if timing.get("current") == skill:
        return now <= section_deadline(sections, timing) + SAVE_GRACE
    # The autosave of the section that has just closed may arrive a moment late (also for Writing, the last one).
    closed_at = (timing.get("closed_at") or {}).get(skill)
    if closed_at and timing["closed"] and timing["closed"][-1] == skill:
        return now <= _at(closed_at) + SAVE_GRACE
    return False


def view(sections: dict, timing: dict, now: datetime, speaking_done: bool) -> dict:
    deadline = section_deadline(sections, timing)
    return {"current": timing.get("current"), "current_deadline": deadline.isoformat() if deadline else None, "closed": timing.get("closed", []),
            "written_started": bool(timing.get("written_started")), "written_done": written_done(timing), "speaking_done": speaking_done,
            "day_deadline": timing["day_deadline"], "day_over": day_over(timing, now),
            "minutes": {skill: round(sections[skill].get("duration_seconds", 0) / 60) for skill in (*WRITTEN, "speaking")}}
