from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class ShowType(str, Enum):
    MOVIE = "movie"
    TV = "tv"
    VARIETY = "variety"
    ANIME = "anime"
    UNKNOWN = "unknown"


class ShowStatus(str, Enum):
    AIRING = "airing"
    UPCOMING = "upcoming"
    ENDED = "ended"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


def _parse_date(val: str | date | None) -> Optional[date]:
    if val is None or val == "":
        return None
    if isinstance(val, date):
        return val
    val = str(val).strip()
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y年%m月%d日",
        "%Y-%m",
        "%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _date_to_str(d: Optional[date]) -> str:
    return d.isoformat() if d else ""


@dataclass
class Show:
    title_cn: str = ""
    title_en: str = ""
    year: Optional[int] = None
    release_date: Optional[date] = None
    first_air_date: Optional[date] = None
    last_air_date: Optional[date] = None
    next_episode_date: Optional[date] = None
    show_type: ShowType = ShowType.UNKNOWN
    status: ShowStatus = ShowStatus.UNKNOWN
    season: Optional[int] = None
    episode: Optional[int] = None
    director: str = ""
    cast: str = ""
    genre: str = ""
    duration: str = ""
    platform: str = ""
    poster_url: str = ""
    tmdb_id: Optional[int] = None
    imdb_id: str = ""
    rating: Optional[float] = None
    notes: str = ""
    raw_title: str = ""

    _MISSING_FIELDS_KEY = "missing_fields"
    _DATE_FIELDS = {
        "release_date",
        "first_air_date",
        "last_air_date",
        "next_episode_date",
    }

    def missing_fields(self) -> list[str]:
        result = []
        skip = {"raw_title", "notes", "tmdb_id", "imdb_id", "rating"}
        for f in fields(self):
            if f.name in skip:
                continue
            val = getattr(self, f.name)
            if val is None or val == "" or val == ShowType.UNKNOWN or val == ShowStatus.UNKNOWN:
                result.append(f.name)
        return result

    def primary_date(self) -> Optional[date]:
        if self.next_episode_date:
            return self.next_episode_date
        if self.first_air_date:
            return self.first_air_date
        if self.release_date:
            return self.release_date
        if self.last_air_date:
            return self.last_air_date
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        for df in self._DATE_FIELDS:
            val = getattr(self, df)
            d[df] = _date_to_str(val)
        d[self._MISSING_FIELDS_KEY] = self.missing_fields()
        d["show_type"] = self.show_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Show:
        d = dict(d)
        d.pop(cls._MISSING_FIELDS_KEY, None)
        if "show_type" in d and isinstance(d["show_type"], str):
            try:
                d["show_type"] = ShowType(d["show_type"])
            except ValueError:
                d["show_type"] = ShowType.UNKNOWN
        if "status" in d and isinstance(d["status"], str):
            try:
                d["status"] = ShowStatus(d["status"])
            except ValueError:
                d["status"] = ShowStatus.UNKNOWN
        for df in cls._DATE_FIELDS:
            if df in d:
                d[df] = _parse_date(d[df])
        field_names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in field_names})


class ShowDatabase:
    def __init__(self, path: Path | None = None):
        self.path = path or Path("show_db.json")
        self.shows: list[Show] = []
        if self.path.exists():
            self._load()

    def _load(self):
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.shows = [Show.from_dict(d) for d in raw]

    def save(self):
        data = [s.to_dict() for s in self.shows]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, show: Show) -> bool:
        for existing in self.shows:
            if _is_duplicate(existing, show):
                return False
        self.shows.append(show)
        return True

    def merge(self, show: Show) -> Show:
        for existing in self.shows:
            if _is_duplicate(existing, show):
                for f in fields(show):
                    new_val = getattr(show, f.name)
                    old_val = getattr(existing, f.name)
                    if _is_better_value(old_val, new_val):
                        setattr(existing, f.name, new_val)
                return existing
        self.shows.append(show)
        return show

    def find_by_title(self, title: str) -> Optional[Show]:
        t = title.strip().lower()
        for s in self.shows:
            if s.title_cn.lower() == t or s.title_en.lower() == t:
                return s
        return None


def _is_better_value(old_val, new_val) -> bool:
    if new_val is None or new_val == "":
        return False
    if old_val is None or old_val == "":
        return True
    if isinstance(old_val, ShowType) and old_val == ShowType.UNKNOWN:
        return True
    if isinstance(old_val, ShowStatus) and old_val == ShowStatus.UNKNOWN:
        return True
    return False


def _is_duplicate(a: Show, b: Show) -> bool:
    if a.tmdb_id and b.tmdb_id and a.tmdb_id == b.tmdb_id:
        return True
    ta = (a.title_cn.strip().lower(), a.title_en.strip().lower(), a.year)
    tb = (b.title_cn.strip().lower(), b.title_en.strip().lower(), b.year)
    if ta[0] and ta[0] == tb[0] and ta[2] == tb[2]:
        return True
    if ta[1] and ta[1] == tb[1] and ta[2] == tb[2]:
        return True
    return False


_CN_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_EN_PATTERN = re.compile(r"[a-zA-Z]")
_YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}")
_DATE_PATTERN = re.compile(r"(?:19|20)\d{2}[-/.年](?:0[1-9]|1[0-2])[-/.月](?:0[1-9]|[12]\d|3[01])日?")
_SEASON_PATTERN = re.compile(r"[Ss](\d+)|第(\d+)季|Season\s*(\d+)", re.IGNORECASE)
_EPISODE_PATTERN = re.compile(r"[Ee](\d+)|第(\d+)集|EP?(\d+)", re.IGNORECASE)
_STATUS_MAP = {
    "播出中": ShowStatus.AIRING,
    "连载中": ShowStatus.AIRING,
    "更新中": ShowStatus.AIRING,
    "即将上映": ShowStatus.UPCOMING,
    "待播": ShowStatus.UPCOMING,
    "已完结": ShowStatus.ENDED,
    "完结": ShowStatus.ENDED,
    "已取消": ShowStatus.CANCELLED,
    "取消": ShowStatus.CANCELLED,
}
_TYPE_MAP = {
    "电影": ShowType.MOVIE,
    "movie": ShowType.MOVIE,
    "电视剧": ShowType.TV,
    "tv": ShowType.TV,
    "综艺": ShowType.VARIETY,
    "variety": ShowType.VARIETY,
    "动漫": ShowType.ANIME,
    "anime": ShowType.ANIME,
    "番剧": ShowType.ANIME,
}


def parse_raw_title(raw: str) -> Show:
    raw = raw.strip()
    show = Show(raw_title=raw)

    date_match = _DATE_PATTERN.search(raw)
    if date_match:
        parsed = _parse_date(date_match.group())
        if parsed:
            show.release_date = parsed
            show.first_air_date = parsed
            if not show.year:
                show.year = parsed.year

    year_match = _YEAR_PATTERN.search(raw)
    if year_match and not show.year:
        show.year = int(year_match.group())

    season_match = _SEASON_PATTERN.search(raw)
    if season_match:
        for g in season_match.groups():
            if g:
                show.season = int(g)
                break

    episode_match = _EPISODE_PATTERN.search(raw)
    if episode_match:
        for g in episode_match.groups():
            if g:
                show.episode = int(g)
                break

    for keyword, status in _STATUS_MAP.items():
        if keyword in raw:
            show.status = status
            break

    for keyword, stype in _TYPE_MAP.items():
        if keyword in raw:
            show.show_type = stype
            break

    cleaned = raw
    for p in [_DATE_PATTERN, _YEAR_PATTERN, _SEASON_PATTERN, _EPISODE_PATTERN]:
        cleaned = p.sub("", cleaned)
    for kw in list(_STATUS_MAP.keys()) + list(_TYPE_MAP.keys()):
        cleaned = cleaned.replace(kw, "")
    cleaned = re.sub(r"[【】\[\]()（）/|·–—\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    cn_parts = []
    en_parts = []
    for token in cleaned.split():
        if _CN_PATTERN.search(token):
            cn_parts.append(token)
        elif _EN_PATTERN.search(token):
            en_parts.append(token)

    show.title_cn = "".join(cn_parts)
    show.title_en = " ".join(en_parts)

    if show.title_cn and not show.title_en:
        show.title_cn = cleaned
    elif show.title_en and not show.title_cn:
        show.title_en = cleaned

    return show
