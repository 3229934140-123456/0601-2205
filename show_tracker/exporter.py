from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
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


GroupBy = Literal[
    "year", "year-month", "release_date", "next_update", "recent",
    "genre", "platform", "status", "type",
]
ExportFormat = Literal["markdown", "csv", "json"]


_GROUP_LABELS = {
    "year": "年份",
    "year-month": "年月",
    "release_date": "上线日期",
    "next_update": "更新日期",
    "recent": "时间",
    "genre": "题材",
    "platform": "平台",
    "status": "状态",
    "type": "类型",
}


def export_shows(
    db: ShowDatabase,
    output: Path,
    fmt: ExportFormat = "markdown",
    group_by: GroupBy | None = None,
    status: str | None = None,
    show_type: str | None = None,
) -> Path:
    shows = list(db.shows)

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
        return _export_json(groups, output, group_by)
    elif fmt == "csv":
        return _export_csv(groups, output, group_by)
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
        return _export_json(groups, output, None)
    elif fmt == "csv":
        return _export_csv(groups, output, None)
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
            next_date = s.get("next_episode_date", "")
            next_str = f" — 下集：{next_date}" if next_date else ""
            lines.append(f"- {name}{year_str}{platform_str}{next_str}")

    if summary["upcoming_shows"]:
        lines.append("\n## 🔜 即将上线\n")
        for s in summary["upcoming_shows"]:
            name = s["title_cn"] or s["title_en"]
            date_str = s.get("first_air_date", "") or s.get("release_date", "")
            if date_str:
                date_part = f" ({date_str})"
            elif s.get("year"):
                date_part = f" ({s['year']})"
            else:
                date_part = ""
            lines.append(f"- {name}{date_part}")

    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _group_shows(shows: list[Show], group_by: GroupBy) -> dict[str, list[Show]]:
    if group_by == "recent":
        return _group_by_recent(shows)
    if group_by == "year-month":
        return _group_by_year_month(shows)
    if group_by == "release_date":
        return _group_by_release_date(shows)
    if group_by == "next_update":
        return _group_by_next_update(shows)

    groups: dict[str, list[Show]] = defaultdict(list)
    for show in shows:
        key = _get_group_key(show, group_by)
        groups[key].append(show)
    return dict(sorted(groups.items(), key=lambda x: x[0], reverse=(group_by == "year")))


def _group_by_recent(shows: list[Show]) -> dict[str, list[Show]]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    quarter_start = _quarter_start(today)

    groups: dict[str, list[Show]] = defaultdict(list)
    for show in shows:
        d = show.primary_date()
        if not d:
            groups["未知日期"].append(show)
            continue
        if d >= today:
            if d <= today + timedelta(days=7):
                groups["🔜 一周内更新"].append(show)
            elif d <= today + timedelta(days=30):
                groups["📅 一月内上线"].append(show)
            else:
                groups["⏳ 即将上线"].append(show)
        else:
            if d >= week_start:
                groups["📆 本周上线"].append(show)
            elif d >= month_start:
                groups["📅 本月上线"].append(show)
            elif d >= quarter_start:
                groups["🗓️ 本季上线"].append(show)
            elif d.year == today.year:
                groups["📆 今年上线"].append(show)
            else:
                groups["📚 往期"].append(show)

    order = ["🔜 一周内更新", "📅 一月内上线", "⏳ 即将上线",
             "📆 本周上线", "📅 本月上线", "🗓️ 本季上线",
             "📆 今年上线", "📚 往期", "未知日期"]
    ordered = {}
    for k in order:
        if k in groups:
            ordered[k] = groups[k]
    return ordered


def _group_by_year_month(shows: list[Show]) -> dict[str, list[Show]]:
    groups: dict[str, list[Show]] = defaultdict(list)
    for show in shows:
        d = show.primary_date()
        if d:
            key = d.strftime("%Y-%m")
        else:
            key = "未知年月"
        groups[key].append(show)
    return dict(sorted(groups.items(), reverse=True))


def _group_by_release_date(shows: list[Show]) -> dict[str, list[Show]]:
    groups: dict[str, list[Show]] = defaultdict(list)
    for show in shows:
        d = show.primary_date()
        if d:
            key = d.isoformat()
        else:
            key = "未知日期"
        groups[key].append(show)
    return dict(sorted(groups.items(), reverse=True))


def _group_by_next_update(shows: list[Show]) -> dict[str, list[Show]]:
    today = date.today()
    groups: dict[str, list[Show]] = defaultdict(list)
    for show in shows:
        d = show.next_episode_date or show.primary_date()
        if d:
            if d >= today:
                diff = (d - today).days
                if diff <= 7:
                    key = f"未来7天内"
                elif diff <= 30:
                    key = f"未来30天内"
                else:
                    key = f"更远的将来"
            else:
                diff = (today - d).days
                if diff <= 7:
                    key = "过去7天内"
                elif diff <= 30:
                    key = "过去30天内"
                else:
                    key = "更早更新"
        else:
            key = "更新时间未知"
        groups[key].append(show)

    order = ["未来7天内", "未来30天内", "更远的将来",
             "过去7天内", "过去30天内", "更早更新",
             "更新时间未知"]
    ordered = {}
    for k in order:
        if k in groups:
            ordered[k] = groups[k]
    return ordered


def _quarter_start(d: date) -> date:
    quarter = (d.month - 1) // 3 * 3 + 1
    return d.replace(month=quarter, day=1)


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


def _export_json(groups: dict[str, list[Show]], output: Path, group_by: GroupBy | None) -> Path:
    group_label = _GROUP_LABELS.get(group_by or "分组")
    data = {
        "_meta": {
            "group_by": group_by or "",
            "group_label": group_label,
            "total_count": sum(len(v) for v in groups.values()),
            "exported_at": datetime.now().isoformat(),
        }
    }
    for group_name, shows in groups.items():
        data[group_name] = [s.to_dict() for s in shows]
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _export_csv(groups: dict[str, list[Show]], output: Path, group_by: GroupBy | None) -> Path:
    headers = [
        "group_name", "group_category",
        "title_cn", "title_en", "year",
        "release_date", "first_air_date", "last_air_date", "next_episode_date",
        "show_type", "status", "season", "episode",
        "director", "cast", "genre", "duration", "platform",
        "poster_url", "rating", "tmdb_id", "imdb_id",
        "notes", "missing_fields",
    ]

    group_label = _GROUP_LABELS.get(group_by or "全部")

    with open(output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for group_name, shows in groups.items():
            for show in shows:
                d = show.to_dict()
                row = {h: d.get(h, "") for h in headers if h not in ("group_name", "group_category")}
                row["group_name"] = group_name
                row["group_category"] = group_label
                if isinstance(row.get("missing_fields"), list):
                    row["missing_fields"] = "; ".join(row["missing_fields"])
                writer.writerow(row)
    return output


def _export_markdown(
    groups: dict[str, list[Show]],
    output: Path,
    group_by: GroupBy | None,
) -> Path:
    lines = []
    today = date.today().isoformat()

    if not group_by:
        lines.append(f"# 影视追踪清单")
        lines.append(f"> 导出日期：{today} | 共 {sum(len(v) for v in groups.values())} 条\n")
    else:
        lines.append(f"# 影视追踪清单（按{_GROUP_LABELS.get(group_by, '分组')}）")
        lines.append(f"> 导出日期：{today} | 共 {sum(len(v) for v in groups.values())} 条\n")

    for group_name, shows in groups.items():
        if group_by:
            subtitle = _format_group_header(group_name, group_by)
            lines.append(f"## {subtitle}")
            lines.append(f"> {len(shows)} 条\n")
        else:
            lines.append(f"## {group_name}\n")

        lines.append("| 片名 | 英文名 | 年份 | 上线日期 | 类型 | 状态 | 季/集 | 平台 | 评分 | 备注 |")
        lines.append("|------|--------|------|----------|------|------|-------|------|------|------|")

        for show in shows:
            name = show.title_cn or "-"
            en = show.title_en or "-"
            year = str(show.year) if show.year else "-"
            release_date = _format_show_date(show)
            stype = _type_display(show.show_type)
            status = _status_display(show.status)
            season_ep = _format_season_ep(show)
            platform = show.platform or "-"
            rating = str(show.rating) if show.rating else "-"
            missing = show.missing_fields()
            note_parts = []
            if missing:
                note_parts.append(f"⚠️ 缺:{','.join(missing[:3])}")
            if show.next_episode_date:
                note_parts.append(f"下集:{show.next_episode_date.isoformat()}")
            note = "; ".join(note_parts) or "-"
            if missing:
                name = f"{name} ⚠️"

            lines.append(f"| {name} | {en} | {year} | {release_date} | {stype} | {status} | {season_ep} | {platform} | {rating} | {note} |")

        lines.append("")

    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _format_group_header(name: str, group_by: GroupBy) -> str:
    if group_by == "year":
        if name == "未知年份":
            return name
        return f"{name} 年"
    if group_by == "year-month":
        if name == "未知年月":
            return name
        try:
            dt = datetime.strptime(name, "%Y-%m")
            return f"{dt.year} 年 {dt.month} 月"
        except ValueError:
            return name
    if group_by == "release_date":
        if name == "未知日期":
            return name
        return f"上线日期：{name}"
    if group_by == "next_update":
        return f"更新：{name}"
    if group_by == "recent":
        return name
    return name


def _format_show_date(show: Show) -> str:
    d = show.primary_date()
    if d:
        return d.isoformat()
    return "-"


def _format_season_ep(show: Show) -> str:
    parts = []
    if show.season:
        parts.append(f"S{show.season:02d}")
    if show.episode:
        parts.append(f"E{show.episode:02d}")
    return "".join(parts) or "-"


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
