from __future__ import annotations

import os
from datetime import date, datetime
from typing import Optional

import httpx

from .models import Show, ShowDatabase, ShowType, ShowStatus, _parse_date


TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


STREAMING_KEYWORDS = [
    "Netflix", "Disney+", "Disney Plus", "HBO Max", "HBO", "Amazon Prime Video",
    "Prime Video", "Apple TV+", "Apple TV", "Hulu", "Paramount+", "Peacock",
    "Max", "Crunchyroll", "Funimation", "Disney+ Hotstar", "Hotstar",
    "腾讯视频", "爱奇艺", "优酷", "芒果TV", "芒果 TV", "B站", "bilibili",
    "哔哩哔哩", "iQIYI", "Youku", "Mango TV", "Tencent Video",
]


class TMDBClient:
    def __init__(self, api_key: str | None = None, language: str = "zh-CN", region: str = "US"):
        self.api_key = api_key or os.getenv("TMDB_API_KEY", "")
        self.language = language
        self.region = region
        self.client = httpx.Client(timeout=15.0)

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        if not self.api_key:
            return None
        p = {"api_key": self.api_key, "language": self.language}
        if params:
            p.update(params)
        try:
            resp = self.client.get(f"{TMDB_BASE}{path}", params=p)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError):
            return None

    def search_movie(self, query: str, year: int | None = None) -> list[dict]:
        params: dict = {"query": query}
        if year:
            params["year"] = year
        result = self._get("/search/movie", params)
        return result.get("results", [])[:5] if result else []

    def search_tv(self, query: str, first_air_date_year: int | None = None) -> list[dict]:
        params: dict = {"query": query}
        if first_air_date_year:
            params["first_air_date_year"] = first_air_date_year
        result = self._get("/search/tv", params)
        return result.get("results", [])[:5] if result else []

    def get_movie_detail(self, movie_id: int) -> dict | None:
        return self._get(f"/movie/{movie_id}", {"append_to_response": "credits,release_dates"})

    def get_tv_detail(self, tv_id: int) -> dict | None:
        return self._get(f"/tv/{tv_id}", {"append_to_response": "credits,next_episode_to_air,last_episode_to_air"})

    def get_movie_watch_providers(self, movie_id: int) -> dict | None:
        return self._get(f"/movie/{movie_id}/watch/providers")

    def get_tv_watch_providers(self, tv_id: int) -> dict | None:
        return self._get(f"/tv/{tv_id}/watch/providers")

    def match_show(self, show: Show) -> Optional[dict]:
        query = show.title_en or show.title_cn
        if not query:
            return None

        is_tv = show.show_type in (ShowType.TV, ShowType.ANIME, ShowType.VARIETY)
        year = show.year

        if is_tv:
            results = self.search_tv(query, year)
        else:
            results = self.search_movie(query, year)

        if not results:
            alt_query = show.title_cn if query == show.title_en else show.title_en
            if alt_query:
                if is_tv:
                    results = self.search_tv(alt_query, year)
                else:
                    results = self.search_movie(alt_query, year)

        if not results:
            return None

        best = results[0]
        tmdb_id = best.get("id")
        if not tmdb_id:
            return None

        if is_tv:
            return self.get_tv_detail(tmdb_id)
        else:
            return self.get_movie_detail(tmdb_id)

    def get_platforms(self, tmdb_id: int, is_tv: bool) -> str:
        if is_tv:
            providers = self.get_tv_watch_providers(tmdb_id)
        else:
            providers = self.get_movie_watch_providers(tmdb_id)

        if not providers or not providers.get("results"):
            return ""

        results = providers["results"]
        regions_to_try = [self.region, "US", "CN", "JP", "GB"]

        for region in regions_to_try:
            region_data = results.get(region)
            if not region_data:
                continue
            flatrate = region_data.get("flatrate", [])
            if flatrate:
                names = [p.get("provider_name", "") for p in flatrate if p.get("provider_name")]
                if names:
                    return "/".join(dict.fromkeys(names[:3]))

        for region in regions_to_try:
            region_data = results.get(region)
            if not region_data:
                continue
            buy = region_data.get("buy", [])
            rent = region_data.get("rent", [])
            all_providers = buy + rent
            if all_providers:
                names = [p.get("provider_name", "") for p in all_providers if p.get("provider_name")]
                if names:
                    return "/".join(dict.fromkeys(names[:3]))

        return ""

    def enrich_show(self, show: Show) -> bool:
        detail = self.match_show(show)
        if not detail:
            return False

        tmdb_id = detail.get("id")
        if tmdb_id:
            show.tmdb_id = tmdb_id

        is_tv = show.show_type in (ShowType.TV, ShowType.ANIME, ShowType.VARIETY)
        if not is_tv and (detail.get("first_air_date") or detail.get("number_of_seasons")):
            is_tv = True
            if show.show_type == ShowType.UNKNOWN:
                show.show_type = ShowType.TV
        elif not is_tv and detail.get("release_date") and show.show_type == ShowType.UNKNOWN:
            show.show_type = ShowType.MOVIE

        if not show.title_cn:
            show.title_cn = detail.get("name", "") or detail.get("title", "")
        if not show.title_en:
            show.title_en = detail.get("original_name", "") or detail.get("original_title", "")

        release_str = detail.get("release_date", "") or detail.get("first_air_date", "")
        if release_str and not show.year:
            try:
                show.year = int(release_str[:4])
            except (ValueError, IndexError):
                pass

        if release_str:
            parsed_release = _parse_date(release_str)
            if parsed_release:
                if is_tv:
                    if not show.first_air_date:
                        show.first_air_date = parsed_release
                else:
                    if not show.release_date:
                        show.release_date = parsed_release
                if not show.year:
                    show.year = parsed_release.year

        last_air_str = detail.get("last_air_date", "")
        if last_air_str and is_tv and not show.last_air_date:
            parsed = _parse_date(last_air_str)
            if parsed:
                show.last_air_date = parsed

        next_ep = detail.get("next_episode_to_air")
        if next_ep and isinstance(next_ep, dict):
            ep_date_str = next_ep.get("air_date", "")
            if ep_date_str and not show.next_episode_date:
                parsed = _parse_date(ep_date_str)
                if parsed:
                    show.next_episode_date = parsed
                    ep_num = next_ep.get("episode_number")
                    if ep_num and not show.episode:
                        show.episode = ep_num
                    season_num = next_ep.get("season_number")
                    if season_num and not show.season:
                        show.season = season_num

        if not show.genre and detail.get("genres"):
            show.genre = "/".join(g["name"] for g in detail["genres"])

        if not show.duration:
            runtime = detail.get("runtime") or detail.get("episode_run_time")
            if runtime:
                if isinstance(runtime, list):
                    runtime = runtime[0] if runtime else None
                if runtime:
                    show.duration = f"{runtime}分钟"

        if not show.poster_url and detail.get("poster_path"):
            show.poster_url = f"{TMDB_IMAGE_BASE}{detail['poster_path']}"

        if not show.rating and detail.get("vote_average"):
            show.rating = round(detail["vote_average"], 1)

        if detail.get("status") and show.status == ShowStatus.UNKNOWN:
            status_map = {
                "Released": ShowStatus.ENDED,
                "Post Production": ShowStatus.UPCOMING,
                "In Production": ShowStatus.AIRING,
                "Returning Series": ShowStatus.AIRING,
                "Ended": ShowStatus.ENDED,
                "Canceled": ShowStatus.CANCELLED,
                "Planned": ShowStatus.UPCOMING,
                "Pilot": ShowStatus.UPCOMING,
                "Filming": ShowStatus.AIRING,
                "Pre-production": ShowStatus.UPCOMING,
            }
            mapped = status_map.get(detail["status"])
            if mapped:
                show.status = mapped

        credits = detail.get("credits", {})
        if credits:
            if not show.director:
                directors = [c for c in credits.get("crew", []) if c.get("job") == "Director"]
                if directors:
                    show.director = "/".join(d["name"] for d in directors[:3])

            if not show.cast:
                cast_list = credits.get("cast", [])[:5]
                if cast_list:
                    show.cast = "/".join(c["name"] for c in cast_list)

        if tmdb_id and not show.platform:
            platforms = self.get_platforms(tmdb_id, is_tv)
            if platforms:
                show.platform = platforms

        if not show.season and detail.get("number_of_seasons"):
            show.season = detail["number_of_seasons"]

        if detail.get("imdb_id") and not show.imdb_id:
            show.imdb_id = detail["imdb_id"]

        return True


def match_all(db: ShowDatabase, api_key: str | None = None, only_missing: bool = True, region: str = "US") -> dict:
    client = TMDBClient(api_key, region=region)
    stats = {"matched": 0, "skipped": 0, "failed": 0}

    if not client.api_key:
        return {"error": "TMDB_API_KEY not set. Set it via --api-key or TMDB_API_KEY env var."}

    for show in db.shows:
        if only_missing and not show.missing_fields():
            stats["skipped"] += 1
            continue
        ok = client.enrich_show(show)
        if ok:
            stats["matched"] += 1
        else:
            stats["failed"] += 1

    db.save()
    return stats


def report_missing(db: ShowDatabase) -> list[dict]:
    report = []
    for show in db.shows:
        missing = show.missing_fields()
        if missing:
            report.append({
                "title_cn": show.title_cn,
                "title_en": show.title_en,
                "year": show.year,
                "missing_fields": missing,
            })
    return report
