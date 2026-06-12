from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Literal

from .models import Show, ShowDatabase, ShowStatus, ShowType
from .updater import (
    generate_ranking,
    generate_translation_list,
    generate_update_reminders,
    generate_watchlist,
    generate_weekly_summary,
)


GroupBy = Literal["year", "genre", "platform", "status", "type"]
ExportFormat = Literal["markdown", "csv", "json"]


def export_shows(
    db: ShowDatabase,
    output: Path,
    fmt: ExportFormat = "markdown",
    group_by: GroupBy | None = None,
    status: str | None = None,
    show_type: str | None = None,
) -> Path:
    shows = db.shows

    if status:
        try:
            st = ShowStatus(status)
            shows = [s for s in shows if s.status == st]
        except ValueError:
            pass

    if show_type:
        try:
            st = ShowType(show_type)
            shows = [s for s in shows if s.show_type == st]
        except ValueError:
            pass

    if group_by:
        groups = _group_shows(shows, group_by)
    else:
        groups = {"全部": shows}

    if fmt == "json":
        return _export_json(groups, output)
    elif fmt == "csv":
        return _export_csv(groups, output)
    else:
        return _export_markdown(groups, output, group_by)


def export_watchlist(
    db: ShowDatabase,
    output: Path,
    fmt: ExportFormat = "markdown",
    status: str | None = None,
    show_type: str | None = None,
) -> Path:
    st = None
    if status:
        try:
            st = ShowStatus(status)
        except ValueError:
            pass
    tp = None
    if show_type:
        try:
            tp = ShowType(show_type)
        except ValueError:
            pass

    shows = generate_watchlist(db, status=st, show_type=tp)
    groups = {"追剧清单": shows}

    if fmt == "json":
        return _export_json(groups, output)
    elif fmt == "csv":
        return _export_csv(groups, output)
    else:
        return _export_markdown(groups, output, None)


def export_reminders(db: ShowDatabase, output: Path, fmt: ExportFormat = "markdown") -> Path:
    reminders = generate_update_reminders(db)
    if fmt == "json":
        output.write_text(json.dumps(reminders, ensure_ascii=False, indent=2), encoding="utf-8")
        return output
    elif fmt == "csv":
        return _export_dict_list_csv(reminders, output)
    else:
        lines = ["# 📺 更新提醒\n"]
        for r in reminders:
            lines.append(f"- {r['message']}")
        output.write_text("\n".join(lines), encoding="utf-8")
        return output


def export_translation_list(db: ShowDatabase, output: Path, fmt: ExportFormat = "markdown") -> Path:
    items = generate_translation_list(db)
    if fmt == "json":
        output.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        return output
    elif fmt == "csv":
        return _export_dict_list_csv(items, output)
    else:
        lines = ["# 🌐 待翻译列表\n"]
        for item in items:
            name = item["title_cn"] or item["title_en"]
            year = item.get("year", "")
            year_str = f" ({year})" if year else ""
            reason = item.get("reason", "")
            lines.append(f"- **{name}{year_str}** — {reason}")
        output.write_text("\n".join(lines), encoding="utf-8")
        return output


def export_ranking(db: ShowDatabase, output: Path, fmt: ExportFormat = "markdown", top_n: int = 10) -> Path:
    ranking = generate_ranking(db, top_n=top_n)
    if fmt == "json":
        output.write_text(json.dumps(ranking, ensure_ascii=False, indent=2), encoding="utf-8")
        return output
    elif fmt == "csv":
        return _export_dict_list_csv(ranking, output)
    else:
        lines = ["# 🏆 推荐榜单\n"]
        for r in ranking:
            name = r["title_cn"] or r["title_en"]
            year = r.get("year", "")
            rating = r.get("rating", "N/A")
            genre = r.get("genre", "")
            year_str = f" ({year})" if year else ""
            lines.append(f"{r['rank']}. **{name}{year_str}** ⭐{rating} {genre}")
        output.write_text("\n".join(lines), encoding="utf-8")
        return output


def export_weekly_summary(db: ShowDatabase, output: Path) -> Path:
    summary = generate_weekly_summary(db)
    lines = [
        f"# 📋 周报 — {summary['date']}\n",
        f"- 追踪总数：{summary['total']}",
        f"- 播出中：{summary['airing_count']}",
        f"- 即将上线：{summary['upcoming_count']}",
        f"- 已完结：{summary['ended_count']}",
        f"- 待翻译：{summary['translation_pending_count']}\n",
    ]

    if summary["airing_shows"]:
        lines.append("## 📺 播出中\n")
        for s in summary["airing_shows"]:
            name = s["title_cn"] or s["title_en"]
            year = s.get("year", "")
            platform = s.get("platform", "")
            year_str = f" ({year})" if year else ""
            platform_str = f" [{platform}]" if platform else ""
            lines.append(f"- {name}{year_str}{platform_str}")

    if summary["upcoming_shows"]:
        lines.append("\n## 🔜 即将上线\n")
        for s in summary["upcoming_shows"]:
            name = s["title_cn"] or s["title_en"]
            year = s.get("year", "")
            year_str = f" ({year})" if year else ""
            lines.append(f"- {name}{year_str}")

    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _group_shows(shows: list[Show], group_by: GroupBy) -> dict[str, list[Show]]:
    groups: dict[str, list[Show]] = defaultdict(list)
    for show in shows:
        key = _get_group_key(show, group_by)
        groups[key].append(show)
    return dict(groups)


def _get_group_key(show: Show, group_by: GroupBy) -> str:
    if group_by == "year":
        return str(show.year or "未知年份")
    elif group_by == "genre":
        genres = show.genre.split("/") if show.genre else []
        return genres[0] if genres else "未知类型"
    elif group_by == "platform":
        platforms = show.platform.split("/") if show.platform else []
        return platforms[0] if platforms else "未知平台"
    elif group_by == "status":
        status_map = {
            ShowStatus.AIRING: "播出中",
            ShowStatus.UPCOMING: "即将上线",
            ShowStatus.ENDED: "已完结",
            ShowStatus.CANCELLED: "已取消",
            ShowStatus.UNKNOWN: "未知状态",
        }
        return status_map.get(show.status, "未知状态")
    elif group_by == "type":
        type_map = {
            ShowType.MOVIE: "电影",
            ShowType.TV: "电视剧",
            ShowType.VARIETY: "综艺",
            ShowType.ANIME: "动漫",
            ShowType.UNKNOWN: "未知类型",
        }
        return type_map.get(show.show_type, "未知类型")
    return "其他"


def _export_json(groups: dict[str, list[Show]], output: Path) -> Path:
    data = {}
    for group_name, shows in groups.items():
        data[group_name] = [s.to_dict() for s in shows]
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _export_csv(groups: dict[str, list[Show]], output: Path) -> Path:
    headers = ["title_cn", "title_en", "year", "show_type", "status", "season", "episode",
               "director", "cast", "genre", "duration", "platform", "poster_url", "rating",
               "notes", "missing_fields"]

    with open(output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for shows in groups.values():
            for show in shows:
                d = show.to_dict()
                row = {h: d.get(h, "") for h in headers}
                if isinstance(row.get("missing_fields"), list):
                    row["missing_fields"] = "; ".join(row["missing_fields"])
                writer.writerow(row)
    return output


def _export_markdown(groups: dict[str, list[Show]], output: Path, group_by: GroupBy | None) -> Path:
    lines = []
    for group_name, shows in groups.items():
        if group_by:
            lines.append(f"## {group_name}\n")
        else:
            lines.append(f"# 影视追踪清单\n")

        lines.append("| 片名 | 英文名 | 年份 | 类型 | 状态 | 季/集 | 平台 | 评分 |")
        lines.append("|------|--------|------|------|------|-------|------|------|")

        for show in shows:
            name = show.title_cn or "-"
            en = show.title_en or "-"
            year = str(show.year) if show.year else "-"
            stype = _type_display(show.show_type)
            status = _status_display(show.status)
            season_ep = ""
            if show.season:
                season_ep += f"S{show.season:02d}"
            if show.episode:
                season_ep += f"E{show.episode:02d}"
            if not season_ep:
                season_ep = "-"
            platform = show.platform or "-"
            rating = str(show.rating) if show.rating else "-"
            missing = show.missing_fields()
            if missing:
                name = f"{name} ⚠️"

            lines.append(f"| {name} | {en} | {year} | {stype} | {status} | {season_ep} | {platform} | {rating} |")

        lines.append("")

    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _export_dict_list_csv(items: list[dict], output: Path) -> Path:
    if not items:
        output.write_text("", encoding="utf-8")
        return output

    headers = list(items[0].keys())
    with open(output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for item in items:
            row = {}
            for h in headers:
                val = item.get(h, "")
                if isinstance(val, list):
                    val = "; ".join(str(v) for v in val)
                row[h] = val
            writer.writerow(row)
    return output


def _type_display(st: ShowType) -> str:
    return {
        ShowType.MOVIE: "电影",
        ShowType.TV: "电视剧",
        ShowType.VARIETY: "综艺",
        ShowType.ANIME: "动漫",
        ShowType.UNKNOWN: "未知",
    }.get(st, "未知")


def _status_display(st: ShowStatus) -> str:
    return {
        ShowStatus.AIRING: "播出中",
        ShowStatus.UPCOMING: "即将上线",
        ShowStatus.ENDED: "已完结",
        ShowStatus.CANCELLED: "已取消",
        ShowStatus.UNKNOWN: "未知",
    }.get(st, "未知")
