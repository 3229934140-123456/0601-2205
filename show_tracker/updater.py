from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from .models import Show, ShowDatabase, ShowStatus, ShowType


def generate_watchlist(db: ShowDatabase, status: ShowStatus | None = None, show_type: ShowType | None = None) -> list[Show]:
    shows = db.shows
    if status:
        shows = [s for s in shows if s.status == status]
    if show_type:
        shows = [s for s in shows if s.show_type == show_type]
    shows.sort(key=lambda s: _sort_key(s), reverse=True)
    return shows


def _sort_key(show: Show) -> tuple:
    d = show.primary_date()
    if d:
        return (1, d.toordinal(), show.title_cn or show.title_en)
    return (0, show.year or 0, show.title_cn or show.title_en)


def generate_update_reminders(db: ShowDatabase) -> list[dict]:
    reminders = []
    airing = [s for s in db.shows if s.status == ShowStatus.AIRING]
    today = date.today()

    sorted_airing = sorted(airing, key=lambda s: (
        (s.next_episode_date or date.min).toordinal(),
        s.title_cn or s.title_en
    ), reverse=False)

    for show in sorted_airing:
        has_next = show.next_episode_date is not None
        next_date = show.next_episode_date
        days_until = None
        if next_date:
            days_until = (next_date - today).days

        reminder = {
            "title_cn": show.title_cn,
            "title_en": show.title_en,
            "season": show.season,
            "episode": show.episode,
            "next_episode_date": next_date.isoformat() if next_date else "",
            "days_until": days_until,
            "platform": show.platform,
            "has_next_date": has_next,
            "message": _build_reminder_message(show, today),
        }
        reminders.append(reminder)

    reminders.sort(key=lambda r: (
        0 if r["has_next_date"] and r["days_until"] is not None and r["days_until"] >= 0 else 1,
        r["days_until"] if r["days_until"] is not None else 9999,
        r["title_cn"] or r["title_en"]
    ))

    return reminders


def _build_reminder_message(show: Show, today: date) -> str:
    name = show.title_cn or show.title_en
    platform = show.platform or "未知平台"

    if show.next_episode_date:
        next_date = show.next_episode_date
        season_str = f"S{show.season:02d}" if show.season else ""
        ep_str = f"E{show.episode:02d}" if show.episode else ""
        season_ep = f"{season_str}{ep_str}".strip()

        days_until = (next_date - today).days
        if days_until < 0:
            when = f"已于 {next_date.isoformat()} 更新"
        elif days_until == 0:
            when = "今天更新"
        elif days_until == 1:
            when = "明天更新"
        elif days_until <= 7:
            when = f"{days_until} 天后更新"
        else:
            when = f"{next_date.isoformat()} 更新"

        if season_ep:
            return f"📅 {name} {season_ep} 将于 {when} [{platform}]"
        else:
            return f"📅 {name} 将于 {when} [{platform}]"

    season_ep = ""
    if show.season:
        season_ep += f"S{show.season:02d}"
    if show.episode:
        season_ep += f"E{show.episode:02d}"

    if season_ep:
        return f"📺 {name} {season_ep} 正在 {platform} 热播中"
    return f"📺 {name} 正在 {platform} 播出中"


def generate_translation_list(db: ShowDatabase) -> list[dict]:
    pending = []
    for show in db.shows:
        has_cn = bool(show.title_cn.strip())
        has_en = bool(show.title_en.strip())
        needs_translate = False
        reason = ""

        if not has_cn and has_en:
            needs_translate = True
            reason = "缺中文名"
        elif has_cn and not has_en:
            needs_translate = True
            reason = "缺英文名"

        if not show.director:
            needs_translate = True
            reason += "; 缺导演" if reason else "缺导演"
        if not show.cast:
            needs_translate = True
            reason += "; 缺主演" if reason else "缺主演"
        if not show.genre:
            needs_translate = True
            reason += "; 缺类型" if reason else "缺类型"

        if needs_translate:
            pending.append({
                "title_cn": show.title_cn,
                "title_en": show.title_en,
                "year": show.year,
                "show_type": show.show_type.value,
                "reason": reason.strip("; "),
                "missing_fields": show.missing_fields(),
            })
    return pending


def generate_ranking(db: ShowDatabase, top_n: int = 10, by: str = "rating") -> list[dict]:
    rated = [s for s in db.shows if s.rating is not None]
    if by == "rating":
        rated.sort(key=lambda s: s.rating or 0, reverse=True)
    else:
        rated.sort(key=lambda s: s.year or 0, reverse=True)

    ranking = []
    for i, show in enumerate(rated[:top_n], 1):
        ranking.append({
            "rank": i,
            "title_cn": show.title_cn,
            "title_en": show.title_en,
            "year": show.year,
            "rating": show.rating,
            "genre": show.genre,
            "platform": show.platform,
        })
    return ranking


def generate_weekly_summary(db: ShowDatabase) -> dict:
    airing = [s for s in db.shows if s.status == ShowStatus.AIRING]
    upcoming = [s for s in db.shows if s.status == ShowStatus.UPCOMING]
    ended = [s for s in db.shows if s.status == ShowStatus.ENDED]
    translation_needed = generate_translation_list(db)

    airing_with_next = [s for s in airing if s.next_episode_date]
    airing_without_next = [s for s in airing if not s.next_episode_date]
    airing_sorted = sorted(airing_with_next, key=lambda s: s.next_episode_date or date.min) + airing_without_next

    upcoming_sorted = sorted(upcoming, key=lambda s: s.primary_date() or date.max)

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total": len(db.shows),
        "airing_count": len(airing),
        "upcoming_count": len(upcoming),
        "ended_count": len(ended),
        "translation_pending_count": len(translation_needed),
        "airing_shows": [_show_brief(s) for s in airing_sorted[:20]],
        "upcoming_shows": [_show_brief(s) for s in upcoming_sorted[:10]],
        "translation_list": translation_needed[:10],
    }


def _show_brief(show: Show) -> dict:
    return {
        "title_cn": show.title_cn,
        "title_en": show.title_en,
        "year": show.year,
        "release_date": show.release_date.isoformat() if show.release_date else "",
        "first_air_date": show.first_air_date.isoformat() if show.first_air_date else "",
        "next_episode_date": show.next_episode_date.isoformat() if show.next_episode_date else "",
        "season": show.season,
        "episode": show.episode,
        "platform": show.platform,
        "genre": show.genre,
        "rating": show.rating,
    }
