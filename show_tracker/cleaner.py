from __future__ import annotations

from .models import Show, ShowDatabase, ShowType, ShowStatus, parse_raw_title, _is_duplicate


def clean_all(db: ShowDatabase, reparse: bool = False) -> dict:
    stats = {"repaired": 0, "merged": 0, "duplicates_removed": 0}
    shows = db.shows

    for show in shows:
        if not show.title_cn and not show.title_en and show.raw_title:
            parsed = parse_raw_title(show.raw_title)
            _fill_empty_from_parsed(show, parsed)
            stats["repaired"] += 1

        if show.show_type == ShowType.UNKNOWN:
            show.show_type = _infer_type(show)
            if show.show_type != ShowType.UNKNOWN:
                stats["repaired"] += 1

        if show.status == ShowStatus.UNKNOWN:
            show.status = _infer_status(show)
            if show.status != ShowStatus.UNKNOWN:
                stats["repaired"] += 1

    merged_set: set[int] = set()
    for i in range(len(shows)):
        if i in merged_set:
            continue
        for j in range(i + 1, len(shows)):
            if j in merged_set:
                continue
            if _is_duplicate(shows[i], shows[j]):
                _merge_into(shows[i], shows[j])
                merged_set.add(j)
                stats["merged"] += 1

    db.shows = [s for i, s in enumerate(shows) if i not in merged_set]
    stats["duplicates_removed"] = len(merged_set)

    db.save()
    return stats


def _fill_empty_from_parsed(target: Show, source: Show) -> None:
    from dataclasses import fields

    for f in fields(target):
        if f.name == "raw_title":
            continue
        new_val = getattr(source, f.name)
        old_val = getattr(target, f.name)
        if (old_val is None or old_val == "" or old_val == ShowType.UNKNOWN or old_val == ShowStatus.UNKNOWN) and new_val not in (None, "", ShowType.UNKNOWN, ShowStatus.UNKNOWN):
            setattr(target, f.name, new_val)


def _merge_into(target: Show, source: Show) -> None:
    from dataclasses import fields

    for f in fields(target):
        if f.name == "raw_title":
            continue
        new_val = getattr(source, f.name)
        old_val = getattr(target, f.name)
        if (old_val is None or old_val == "" or old_val == ShowType.UNKNOWN or old_val == ShowStatus.UNKNOWN) and new_val not in (None, "", ShowType.UNKNOWN, ShowStatus.UNKNOWN):
            setattr(target, f.name, new_val)


def _infer_type(show: Show) -> ShowType:
    title = f"{show.title_cn} {show.title_en} {show.raw_title}".lower()
    anime_kw = ["动漫", "番", "anime", "animation", "cartoon"]
    variety_kw = ["综艺", "variety", "show", "真人秀"]
    movie_kw = ["电影", "movie", "film", "剧场版", "院线"]
    tv_kw = ["电视剧", "tv", "series", "drama", "剧"]

    for kw in anime_kw:
        if kw in title:
            return ShowType.ANIME
    for kw in variety_kw:
        if kw in title:
            return ShowType.VARIETY
    for kw in movie_kw:
        if kw in title:
            return ShowType.MOVIE
    for kw in tv_kw:
        if kw in title:
            return ShowType.TV

    if show.season is not None or show.episode is not None:
        return ShowType.TV

    return ShowType.UNKNOWN


def _infer_status(show: Show) -> ShowStatus:
    notes = f"{show.notes} {show.raw_title}".lower()
    if any(kw in notes for kw in ["播出中", "连载中", "更新中", "airing"]):
        return ShowStatus.AIRING
    if any(kw in notes for kw in ["即将上映", "待播", "upcoming"]):
        return ShowStatus.UPCOMING
    if any(kw in notes for kw in ["已完结", "完结", "ended"]):
        return ShowStatus.ENDED
    if any(kw in notes for kw in ["已取消", "取消", "cancelled"]):
        return ShowStatus.CANCELLED
    return ShowStatus.UNKNOWN
