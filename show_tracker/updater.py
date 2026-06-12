from __future__ import annotations

from datetime import datetime
from typing import Optional

from .models import Show, ShowDatabase, ShowStatus, ShowType


def generate_watchlist(db: ShowDatabase, status: ShowStatus | None = None, show_type: ShowType | None = None) -> list[Show]:
    shows = db.shows
    if status:
        shows = [s for s in shows if s.status == status]
    if show_type:
        shows = [s for s in shows if s.show_type == show_type]
    shows.sort(key=lambda s: (s.year or 0, s.title_cn or s.title_en), reverse=True)
    return shows


def generate_update_reminders(db: ShowDatabase) -> list[dict]:
    reminders = []
    airing = [s for s in db.shows if s.status == ShowStatus.AIRING]
    for show in airing:
        reminders.append({
            "title_cn": show.title_cn,
            "title_en": show.title_en,
            "season": show.season,
            "episode": show.episode,
            "platform": show.platform,
            "message": _build_reminder_message(show),
        })
    return reminders


def _build_reminder_message(show: Show) -> str:
    parts = []
    name = show.title_cn or show.title_en
    if show.season:
        parts.append(f"S{show.season:02d}")
    if show.episode:
        parts.append(f"E{show.episode:02d}")
    season_ep = " ".join(parts)
    platform = show.platform or "未知平台"
    if season_ep:
        return f"📺 {name} {season_ep} 已在 {platform} 更新"
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

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total": len(db.shows),
        "airing_count": len(airing),
        "upcoming_count": len(upcoming),
        "ended_count": len(ended),
        "translation_pending_count": len(translation_needed),
        "airing_shows": [_show_brief(s) for s in airing[:20]],
        "upcoming_shows": [_show_brief(s) for s in upcoming[:10]],
        "translation_list": translation_needed[:10],
    }


def _show_brief(show: Show) -> dict:
    return {
        "title_cn": show.title_cn,
        "title_en": show.title_en,
        "year": show.year,
        "season": show.season,
        "episode": show.episode,
        "platform": show.platform,
        "genre": show.genre,
        "rating": show.rating,
    }
