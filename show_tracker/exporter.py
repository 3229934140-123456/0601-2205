from __future__ import annotations

import csv
import json
import uuid
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
WeeklyTemplate = Literal["subteam", "community", "personal"]


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

_TEMPLATE_NAMES = {
    "subteam": "字幕组周报",
    "community": "观影社群周报",
    "personal": "个人追剧周报",
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
        groups, group_ranges = _group_shows(shows, group_by)
    else:
        groups = {"全部": shows}
        group_ranges = {"全部": ""}

    if fmt == "json":
        return _export_json(groups, output, group_by, group_ranges)
    elif fmt == "csv":
        return _export_csv(groups, output, group_by, group_ranges)
    else:
        return _export_markdown(groups, output, group_by, group_ranges)


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
    group_ranges = {"追剧清单": ""}

    if fmt == "json":
        return _export_json(groups, output, None, group_ranges)
    elif fmt == "csv":
        return _export_csv(groups, output, None, group_ranges)
    else:
        return _export_markdown(groups, output, None, group_ranges)


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


def _group_shows(shows: list[Show], group_by: GroupBy) -> tuple[dict[str, list[Show]], dict[str, str]]:
    group_ranges = {}
    if group_by == "recent":
        groups, group_ranges = _group_by_recent(shows)
        return groups, group_ranges
    if group_by == "year-month":
        groups, group_ranges = _group_by_year_month(shows)
        return groups, group_ranges
    if group_by == "release_date":
        groups, group_ranges = _group_by_release_date(shows)
        return groups, group_ranges
    if group_by == "next_update":
        groups, group_ranges = _group_by_next_update(shows)
        return groups, group_ranges

    groups: dict[str, list[Show]] = defaultdict(list)
    for show in shows:
        key = _get_group_key(show, group_by)
        groups[key].append(show)
    return dict(sorted(groups.items(), key=lambda x: x[0], reverse=(group_by == "year"))), group_ranges


def _group_by_recent(shows: list[Show]) -> dict[str, list[Show]]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)
    next_month = month_start.replace(month=month_start.month + 1 if month_start.month < 12 else 1, year=month_start.year + 1 if month_start.month == 12 else month_start.year)
    month_end = next_month - timedelta(days=1)
    quarter_start = _quarter_start(today)

    groups: dict[str, list[Show]] = defaultdict(list)
    group_ranges: dict[str, str] = {}
    for show in shows:
        d = show.update_date()
        if not d:
            groups["未知日期"].append(show)
            continue
        if d >= today:
            if d <= today + timedelta(days=7):
                key = f"🔜 未来7天更新 ({today.isoformat()} ~ {(today + timedelta(days=7)).isoformat()})"
                groups[key].append(show)
                group_ranges[key] = f"{today.isoformat()}~{(today + timedelta(days=7)).isoformat()}"
            elif d <= today + timedelta(days=30):
                key = f"📅 未来30天上线 ({today.isoformat()} ~ {(today + timedelta(days=30)).isoformat()})"
                groups[key].append(show)
                group_ranges[key] = f"{today.isoformat()}~{(today + timedelta(days=30)).isoformat()}"
            else:
                key = f"⏳ 即将上线 ({(today + timedelta(days=31)).isoformat()} 之后)"
                groups[key].append(show)
                group_ranges[key] = f">{(today + timedelta(days=31)).isoformat()}"
        else:
            if d >= week_start:
                key = f"📆 本周更新 ({week_start.isoformat()} ~ {week_end.isoformat()})"
                groups[key].append(show)
                group_ranges[key] = f"{week_start.isoformat()}~{week_end.isoformat()}"
            elif d >= month_start:
                key = f"📅 本月更新 ({month_start.isoformat()} ~ {month_end.isoformat()})"
                groups[key].append(show)
                group_ranges[key] = f"{month_start.isoformat()}~{month_end.isoformat()}"
            elif d >= quarter_start:
                key = f"🗓️ 本季更新 ({quarter_start.isoformat()} ~ {today.isoformat()})"
                groups[key].append(show)
                group_ranges[key] = f"{quarter_start.isoformat()}~{today.isoformat()}"
            elif d.year == today.year:
                key = f"📆 今年更新 ({today.year}-01-01 ~ {today.isoformat()})"
                groups[key].append(show)
                group_ranges[key] = f"{today.year}-01-01~{today.isoformat()}"
            else:
                key = f"📚 往期 (截至 {quarter_start.isoformat()})"
                groups[key].append(show)
                group_ranges[key] = f"<{quarter_start.isoformat()}"

    order = [k for k in groups if k.startswith("🔜")] + \
            [k for k in groups if k.startswith("📅") and "30" in k] + \
            [k for k in groups if k.startswith("⏳")] + \
            [k for k in groups if k.startswith("📆") and "本周" in k] + \
            [k for k in groups if k.startswith("📅") and "本月" in k] + \
            [k for k in groups if k.startswith("🗓️")] + \
            [k for k in groups if k.startswith("📆") and "今年" in k] + \
            [k for k in groups if k.startswith("📚")] + \
            ["未知日期"]
    ordered = {}
    for k in order:
        if k in groups:
            ordered[k] = groups[k]
    return ordered, group_ranges


def _group_by_year_month(shows: list[Show]) -> tuple[dict[str, list[Show]], dict[str, str]]:
    groups: dict[str, list[Show]] = defaultdict(list)
    group_ranges: dict[str, str] = {}
    for show in shows:
        d = show.primary_date()
        if d:
            ym = d.strftime("%Y-%m")
            month_end = d.replace(day=28) + timedelta(days=4)
            month_end = month_end - timedelta(days=month_end.day)
            key = f"{ym} ({d.strftime('%Y-%m-01')} ~ {month_end.isoformat()})"
            groups[key].append(show)
            group_ranges[key] = f"{d.strftime('%Y-%m-01')}~{month_end.isoformat()}"
        else:
            key = "未知年月"
            groups[key].append(show)
            group_ranges[key] = ""
    return dict(sorted(groups.items(), reverse=True)), group_ranges


def _group_by_release_date(shows: list[Show]) -> tuple[dict[str, list[Show]], dict[str, str]]:
    groups: dict[str, list[Show]] = defaultdict(list)
    group_ranges: dict[str, str] = {}
    for show in shows:
        d = show.primary_date()
        if d:
            key = f"上线日期：{d.isoformat()}"
            groups[key].append(show)
            group_ranges[key] = d.isoformat()
        else:
            key = "未知日期"
            groups[key].append(show)
            group_ranges[key] = ""
    return dict(sorted(groups.items(), reverse=True)), group_ranges


def _group_by_next_update(shows: list[Show]) -> tuple[dict[str, list[Show]], dict[str, str]]:
    today = date.today()
    groups: dict[str, list[Show]] = defaultdict(list)
    group_ranges: dict[str, str] = {}
    for show in shows:
        d = show.update_date()
        if d:
            if d >= today:
                diff = (d - today).days
                if diff <= 7:
                    key = f"未来7天内 ({today.isoformat()} ~ {(today + timedelta(days=7)).isoformat()})"
                    groups[key].append(show)
                    group_ranges[key] = f"{today.isoformat()}~{(today + timedelta(days=7)).isoformat()}"
                elif diff <= 30:
                    key = f"未来30天内 ({today.isoformat()} ~ {(today + timedelta(days=30)).isoformat()})"
                    groups[key].append(show)
                    group_ranges[key] = f"{today.isoformat()}~{(today + timedelta(days=30)).isoformat()}"
                else:
                    key = f"更远的将来 ({(today + timedelta(days=31)).isoformat()} 之后)"
                    groups[key].append(show)
                    group_ranges[key] = f">{(today + timedelta(days=31)).isoformat()}"
            else:
                diff = (today - d).days
                if diff <= 7:
                    key = f"过去7天内 ({(today - timedelta(days=7)).isoformat()} ~ {today.isoformat()})"
                    groups[key].append(show)
                    group_ranges[key] = f"{(today - timedelta(days=7)).isoformat()}~{today.isoformat()}"
                elif diff <= 30:
                    key = f"过去30天内 ({(today - timedelta(days=30)).isoformat()} ~ {today.isoformat()})"
                    groups[key].append(show)
                    group_ranges[key] = f"{(today - timedelta(days=30)).isoformat()}~{today.isoformat()}"
                else:
                    key = f"更早更新 (截至 {(today - timedelta(days=31)).isoformat()})"
                    groups[key].append(show)
                    group_ranges[key] = f"<{(today - timedelta(days=31)).isoformat()}"
        else:
            key = "更新时间未知"
            groups[key].append(show)
            group_ranges[key] = ""

    order = [k for k in groups if k.startswith("未来7天")] + \
            [k for k in groups if k.startswith("未来30天")] + \
            [k for k in groups if k.startswith("更远")] + \
            [k for k in groups if k.startswith("过去7天")] + \
            [k for k in groups if k.startswith("过去30天")] + \
            [k for k in groups if k.startswith("更早")] + \
            ["更新时间未知"]
    ordered = {}
    for k in order:
        if k in groups:
            ordered[k] = groups[k]
    return ordered, group_ranges


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


def _export_json(groups: dict[str, list[Show]], output: Path, group_by: GroupBy | None, group_ranges: dict[str, str]) -> Path:
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
        data[group_name] = {
            "range": group_ranges.get(group_name, ""),
            "count": len(shows),
            "items": [s.to_dict() for s in shows],
        }
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _export_csv(groups: dict[str, list[Show]], output: Path, group_by: GroupBy | None, group_ranges: dict[str, str]) -> Path:
    headers = [
        "group_name", "group_category", "group_range",
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
                row = {h: d.get(h, "") for h in headers if h not in ("group_name", "group_category", "group_range")}
                row["group_name"] = group_name
                row["group_category"] = group_label
                row["group_range"] = group_ranges.get(group_name, "")
                if isinstance(row.get("missing_fields"), list):
                    row["missing_fields"] = "; ".join(row["missing_fields"])
                writer.writerow(row)
    return output


def _export_markdown(
    groups: dict[str, list[Show]],
    output: Path,
    group_by: GroupBy | None,
    group_ranges: dict[str, str],
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
            range_str = group_ranges.get(group_name, "")
            if range_str:
                lines.append(f"> {len(shows)} 条 | 范围：{range_str}\n")
            else:
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


def generate_weekly_report(
    db: ShowDatabase,
    template: WeeklyTemplate = "community",
) -> dict:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_ago = today - timedelta(days=30)
    next_week = today + timedelta(days=7)

    shows = db.shows

    new_released = []
    for s in shows:
        pd = s.primary_date()
        if pd and pd >= month_ago and pd <= today:
            new_released.append(s)
    new_released.sort(key=lambda s: s.primary_date() or date.min, reverse=True)

    upcoming_updates = []
    for s in shows:
        nd = s.update_date()
        if nd and nd >= today and nd <= next_week:
            upcoming_updates.append(s)
    upcoming_updates.sort(key=lambda s: s.update_date() or date.max)

    ended_catchup = []
    for s in shows:
        if s.status == ShowStatus.ENDED:
            pd = s.primary_date()
            if pd and pd >= month_ago:
                ended_catchup.append(s)
    ended_catchup.sort(key=lambda s: s.rating or 0, reverse=True)

    missing_info = []
    for s in shows:
        mf = s.missing_fields()
        if mf:
            missing_info.append(s)

    if template == "subteam":
        missing_info.sort(key=lambda s: len(s.missing_fields()), reverse=True)
    elif template == "personal":
        new_released = [s for s in new_released if s.show_type in (ShowType.TV, ShowType.ANIME, ShowType.MOVIE)]
        upcoming_updates = [s for s in upcoming_updates if s.show_type in (ShowType.TV, ShowType.ANIME)]

    return {
        "template": template,
        "template_name": _TEMPLATE_NAMES.get(template, "周报"),
        "date_range": f"{week_start.isoformat()} ~ {week_end.isoformat()}",
        "generated_at": today.isoformat(),
        "total_count": len(shows),
        "sections": {
            "new_released": {
                "title": "🆕 新上线",
                "subtitle": f"近一个月上线（{month_ago.isoformat()} ~ {today.isoformat()}）",
                "items": [_show_brief_for_weekly(s) for s in new_released],
                "count": len(new_released),
            },
            "upcoming_updates": {
                "title": "🔜 即将更新",
                "subtitle": f"未来7天更新（{today.isoformat()} ~ {next_week.isoformat()}）",
                "items": [_show_brief_for_weekly(s) for s in upcoming_updates],
                "count": len(upcoming_updates),
            },
            "ended_catchup": {
                "title": "✅ 完结可补",
                "subtitle": f"近一个月完结可补番（{month_ago.isoformat()} ~ {today.isoformat()}）",
                "items": [_show_brief_for_weekly(s) for s in ended_catchup],
                "count": len(ended_catchup),
            },
            "missing_info": {
                "title": "⚠️ 资料缺失",
                "subtitle": "以下条目信息待补全",
                "items": [_show_brief_for_weekly(s, include_missing=True) for s in missing_info],
                "count": len(missing_info),
            },
        },
    }


def _show_brief_for_weekly(show: Show, include_missing: bool = False) -> dict:
    brief = {
        "title_cn": show.title_cn,
        "title_en": show.title_en,
        "year": show.year,
        "show_type": _type_display(show.show_type),
        "status": _status_display(show.status),
        "primary_date": show.primary_date().isoformat() if show.primary_date() else "",
        "next_episode_date": show.next_episode_date.isoformat() if show.next_episode_date else "",
        "season": show.season,
        "episode": show.episode,
        "platform": show.platform or "未知平台",
        "genre": show.genre,
        "rating": show.rating,
    }
    if include_missing:
        brief["missing_fields"] = show.missing_fields()
    return brief


def export_weekly_report(
    db: ShowDatabase,
    output: Path,
    template: WeeklyTemplate = "community",
    fmt: ExportFormat = "markdown",
) -> Path:
    report = generate_weekly_report(db, template)

    if fmt == "json":
        return _export_weekly_json(report, output)
    elif fmt == "csv":
        return _export_weekly_csv(report, output)
    else:
        return _export_weekly_markdown(report, output)


def _export_weekly_markdown(report: dict, output: Path) -> Path:
    lines = []
    lines.append(f"# 📋 {report['template_name']}")
    lines.append(f"> 时间范围：{report['date_range']} | 生成时间：{report['generated_at']} | 共追踪 {report['total_count']} 部\n")

    section_order = ["new_released", "upcoming_updates", "ended_catchup", "missing_info"]

    for section_key in section_order:
        section = report["sections"][section_key]
        if not section["items"]:
            continue

        lines.append(f"## {section['title']}")
        lines.append(f"> {section['subtitle']} | 共 {section['count']} 部\n")

        lines.append("| 片名 | 英文名 | 年份 | 日期 | 类型 | 状态 | 季/集 | 平台 | 评分 | 备注 |")
        lines.append("|------|--------|------|------|------|------|-------|------|------|------|")

        for item in section["items"]:
            name = item["title_cn"] or "-"
            en = item["title_en"] or "-"
            year = str(item["year"]) if item["year"] else "-"
            show_date = item["next_episode_date"] or item["primary_date"] or "-"
            stype = item["show_type"]
            status = item["status"]
            season_ep = ""
            if item["season"]:
                season_ep += f"S{item['season']:02d}"
            if item["episode"]:
                season_ep += f"E{item['episode']:02d}"
            season_ep = season_ep or "-"
            platform = item["platform"]
            rating = str(item["rating"]) if item["rating"] else "-"

            note_parts = []
            if item.get("missing_fields"):
                note_parts.append(f"⚠️ 缺:{','.join(item['missing_fields'][:3])}")
            if item["next_episode_date"] and section_key == "upcoming_updates":
                note_parts.append(f"下集:{item['next_episode_date']}")
            note = "; ".join(note_parts) or "-"

            if item.get("missing_fields"):
                name = f"{name} ⚠️"

            lines.append(f"| {name} | {en} | {year} | {show_date} | {stype} | {status} | {season_ep} | {platform} | {rating} | {note} |")
        lines.append("")

    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _export_weekly_csv(report: dict, output: Path) -> Path:
    headers = [
        "section", "section_title", "section_subtitle",
        "title_cn", "title_en", "year", "show_type", "status",
        "primary_date", "next_episode_date",
        "season", "episode", "platform", "genre", "rating",
        "missing_fields",
    ]

    section_order = ["new_released", "upcoming_updates", "ended_catchup", "missing_info"]

    with open(output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for section_key in section_order:
            section = report["sections"][section_key]
            for item in section["items"]:
                row = {
                    "section": section_key,
                    "section_title": section["title"],
                    "section_subtitle": section["subtitle"],
                    "title_cn": item.get("title_cn", ""),
                    "title_en": item.get("title_en", ""),
                    "year": item.get("year", ""),
                    "show_type": item.get("show_type", ""),
                    "status": item.get("status", ""),
                    "primary_date": item.get("primary_date", ""),
                    "next_episode_date": item.get("next_episode_date", ""),
                    "season": item.get("season", ""),
                    "episode": item.get("episode", ""),
                    "platform": item.get("platform", ""),
                    "genre": item.get("genre", ""),
                    "rating": item.get("rating", ""),
                }
                mf = item.get("missing_fields", [])
                if mf:
                    row["missing_fields"] = "; ".join(mf)
                writer.writerow(row)
    return output


def _export_weekly_json(report: dict, output: Path) -> Path:
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def export_calendar(db: ShowDatabase, output: Path) -> Path:
    shows = db.shows
    ical_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Show Tracker//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for show in shows:
        name = show.title_cn or show.title_en or "未知影片"
        platform = show.platform or "未知平台"
        season_ep = ""
        if show.season:
            season_ep += f"S{show.season:02d}"
        if show.episode:
            season_ep += f"E{show.episode:02d}"

        for date_type, d in show.all_dates():
            if not d:
                continue

            dtstart = d.strftime("%Y%m%d")
            dtend = (d + timedelta(days=1)).strftime("%Y%m%d")
            uid = f"{uuid.uuid4().hex}@showtracker"
            dtstamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")

            summary_parts = [date_type, name]
            if season_ep:
                summary_parts.append(season_ep)
            summary = " | ".join(summary_parts)

            description_parts = []
            if show.title_cn and show.title_en:
                description_parts.append(f"中文名: {show.title_cn}")
                description_parts.append(f"英文名: {show.title_en}")
            elif show.title_en:
                description_parts.append(f"原名: {show.title_en}")
            if show.year:
                description_parts.append(f"年份: {show.year}")
            if season_ep:
                description_parts.append(f"季集: {season_ep}")
            description_parts.append(f"平台: {platform}")
            if show.genre:
                description_parts.append(f"类型: {show.genre}")
            if show.rating:
                description_parts.append(f"评分: {show.rating}")
            description = "\\n".join(description_parts)

            event = [
                "BEGIN:VEVENT",
                f"DTSTART;VALUE=DATE:{dtstart}",
                f"DTEND;VALUE=DATE:{dtend}",
                f"DTSTAMP:{dtstamp}",
                f"UID:{uid}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                f"LOCATION:{platform}",
                "END:VEVENT",
            ]
            ical_lines.extend(event)

    ical_lines.append("END:VCALENDAR")
    output.write_text("\r\n".join(ical_lines), encoding="utf-8")
    return output
