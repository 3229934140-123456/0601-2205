from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .models import Show, ShowDatabase, ShowStatus, ShowType
from .importer import import_from_csv, import_from_excel, import_from_text
from .cleaner import clean_all
from .matcher import match_all, report_missing
from .exporter import (
    export_shows,
    export_watchlist,
    export_reminders,
    export_translation_list,
    export_ranking,
    export_weekly_summary,
)

app = typer.Typer(
    name="show-tracker",
    help="影视追踪自动化工具 — 字幕组与观影社群批量整理新片资料",
    no_args_is_help=True,
)
console = Console()


def _db_path(db: str | None) -> Path:
    return Path(db) if db else Path("show_db.json")


@app.command("import", help="从 CSV/Excel/文本文件导入片名")
def import_cmd(
    source: Path = typer.Argument(..., help="源文件路径（.csv / .xlsx / .txt）"),
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
    title_col: str = typer.Option("title", "--col", help="CSV/Excel 中片名列名"),
    merge: bool = typer.Option(False, "--merge", help="合并重复条目而非跳过"),
):
    database = ShowDatabase(_db_path(db))
    ext = source.suffix.lower()

    if ext == ".csv":
        imported = import_from_csv(source, database, title_col, merge)
    elif ext in (".xlsx", ".xls"):
        imported = import_from_excel(source, database, title_col, merge)
    elif ext in (".txt", ".text", ".list"):
        imported = import_from_text(source, database, merge)
    else:
        console.print(f"[red]不支持的文件格式: {ext}[/red]")
        raise typer.Exit(1)

    database.save()
    console.print(f"[green]✓ 成功导入 {len(imported)} 条记录（数据库共 {len(database.shows)} 条）[/green]")


@app.command("clean", help="清洗数据：解析片名、合并重复、推断类型与状态")
def clean_cmd(
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
    reparse: bool = typer.Option(False, "--reparse", help="重新解析所有原始片名"),
):
    database = ShowDatabase(_db_path(db))
    stats = clean_all(database, reparse=reparse)
    console.print(f"[green]✓ 清洗完成：修复 {stats['repaired']} 条 / 合并 {stats['merged']} 条 / 去重 {stats['duplicates_removed']} 条[/green]")


@app.command("match", help="调用 TMDB API 补全影片信息")
def match_cmd(
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="TMDB API Key"),
    region: str = typer.Option("US", "--region", help="流媒体平台地区（US/CN/JP/GB 等）"),
    all_shows: bool = typer.Option(False, "--all", help="匹配所有条目（默认只匹配有缺失字段的）"),
):
    database = ShowDatabase(_db_path(db))
    result = match_all(database, api_key, only_missing=not all_shows, region=region)
    if "error" in result:
        console.print(f"[red]✗ {result['error']}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓ 匹配完成：成功 {result['matched']} / 跳过 {result['skipped']} / 失败 {result['failed']}[/green]")


@app.command("missing", help="检查缺失字段")
def missing_cmd(
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
):
    database = ShowDatabase(_db_path(db))
    report = report_missing(database)
    if not report:
        console.print("[green]✓ 所有条目信息完整，无缺失字段[/green]")
        return

    table = Table(title="缺失字段报告")
    table.add_column("中文名", style="cyan")
    table.add_column("英文名", style="cyan")
    table.add_column("年份")
    table.add_column("缺失字段", style="red")

    for item in report:
        table.add_row(
            item["title_cn"] or "-",
            item["title_en"] or "-",
            str(item.get("year") or "-"),
            ", ".join(item["missing_fields"]),
        )

    console.print(table)
    console.print(f"[yellow]共 {len(report)} 条记录存在缺失字段[/yellow]")


@app.command("update", help="生成追剧清单、更新提醒、待翻译列表、推荐榜单")
def update_cmd(
    report_type: str = typer.Argument("all", help="报告类型：watchlist / reminders / translation / ranking / weekly / all"),
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
    status: Optional[str] = typer.Option(None, "--status", help="按状态筛选：airing / upcoming / ended / cancelled"),
    show_type: Optional[str] = typer.Option(None, "--type", help="按类型筛选：movie / tv / variety / anime"),
    top_n: int = typer.Option(10, "--top", help="推荐榜单数量"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出文件路径"),
    fmt: str = typer.Option("markdown", "--format", help="输出格式：markdown / csv / json"),
):
    database = ShowDatabase(_db_path(db))

    if report_type in ("watchlist", "all"):
        shows = generate_filtered_shows(database, status, show_type)
        _print_watchlist(shows)
        if output and report_type == "watchlist":
            out_path = output
            export_watchlist(database, out_path, fmt, status, show_type)
            console.print(f"[green]✓ 追剧清单已导出到 {out_path}[/green]")

    if report_type in ("reminders", "all"):
        from .updater import generate_update_reminders
        reminders = generate_update_reminders(database)
        _print_reminders(reminders)
        if output and report_type == "reminders":
            export_reminders(database, output, fmt)
            console.print(f"[green]✓ 更新提醒已导出到 {output}[/green]")

    if report_type in ("translation", "all"):
        from .updater import generate_translation_list
        items = generate_translation_list(database)
        _print_translation_list(items)
        if output and report_type == "translation":
            export_translation_list(database, output, fmt)
            console.print(f"[green]✓ 待翻译列表已导出到 {output}[/green]")

    if report_type in ("ranking", "all"):
        from .updater import generate_ranking
        ranking = generate_ranking(database, top_n)
        _print_ranking(ranking)
        if output and report_type == "ranking":
            export_ranking(database, output, fmt, top_n)
            console.print(f"[green]✓ 推荐榜单已导出到 {output}[/green]")

    if report_type == "weekly":
        out_path = output or Path("weekly_summary.md")
        export_weekly_summary(database, out_path)
        console.print(f"[green]✓ 周报已导出到 {out_path}[/green]")


@app.command("export", help="导出影视数据，支持分组与多种格式")
def export_cmd(
    output: Path = typer.Argument(..., help="输出文件路径"),
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
    fmt: str = typer.Option("markdown", "--format", help="输出格式：markdown / csv / json"),
    group_by: Optional[str] = typer.Option(None, "--group-by", help="分组方式：year / year-month / release_date / next_update / recent / genre / platform / status / type"),
    status: Optional[str] = typer.Option(None, "--status", help="按状态筛选"),
    show_type: Optional[str] = typer.Option(None, "--type", help="按类型筛选"),
):
    database = ShowDatabase(_db_path(db))
    export_shows(database, output, fmt, group_by, status, show_type)
    console.print(f"[green]✓ 已导出到 {output}[/green]")


@app.command("list", help="列出数据库中所有影片")
def list_cmd(
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
    status: Optional[str] = typer.Option(None, "--status", help="按状态筛选"),
    show_type: Optional[str] = typer.Option(None, "--type", help="按类型筛选"),
    sort_by: str = typer.Option("date", "--sort", help="排序方式：date / title / rating"),
):
    database = ShowDatabase(_db_path(db))
    shows = list(database.shows)

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

    if sort_by == "date":
        shows.sort(key=lambda s: (s.primary_date() or date.min), reverse=True)
    elif sort_by == "title":
        shows.sort(key=lambda s: s.title_cn or s.title_en)
    elif sort_by == "rating":
        shows.sort(key=lambda s: s.rating or 0, reverse=True)

    table = Table(title=f"影视追踪库（共 {len(shows)} 条）")
    table.add_column("中文名", style="cyan", max_width=20)
    table.add_column("英文名", style="cyan", max_width=25)
    table.add_column("上线日期", width=12)
    table.add_column("下一集", width=12)
    table.add_column("类型", width=6)
    table.add_column("状态", width=8)
    table.add_column("季/集", width=8)
    table.add_column("平台", max_width=15)
    table.add_column("评分", width=5)

    for show in shows:
        name = show.title_cn or "-"
        en = show.title_en or "-"
        release_date = show.primary_date().isoformat() if show.primary_date() else "-"
        next_date = show.next_episode_date.isoformat() if show.next_episode_date else "-"
        stype = _type_short(show.show_type)
        st = _status_short(show.status)
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

        table.add_row(name, en, release_date, next_date, stype, st, season_ep, platform, rating)

    console.print(table)


def generate_filtered_shows(db: ShowDatabase, status: str | None, show_type: str | None) -> list[Show]:
    from .updater import generate_watchlist
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
    return generate_watchlist(db, status=st, show_type=tp)


def _print_watchlist(shows: list[Show]) -> None:
    if not shows:
        console.print("[yellow]追剧清单为空[/yellow]")
        return
    table = Table(title="📺 追剧清单")
    table.add_column("片名", style="cyan")
    table.add_column("上线日期")
    table.add_column("类型")
    table.add_column("状态")
    table.add_column("季/集")
    table.add_column("平台")
    table.add_column("下集")

    for s in shows:
        name = s.title_cn or s.title_en or "-"
        release_date = s.primary_date().isoformat() if s.primary_date() else "-"
        season_ep = ""
        if s.season:
            season_ep += f"S{s.season:02d}"
        if s.episode:
            season_ep += f"E{s.episode:02d}"
        next_ep = s.next_episode_date.isoformat() if s.next_episode_date else "-"
        table.add_row(
            name,
            release_date,
            _type_short(s.show_type),
            _status_short(s.status),
            season_ep or "-",
            s.platform or "-",
            next_ep,
        )
    console.print(table)


def _print_reminders(reminders: list[dict]) -> None:
    if not reminders:
        console.print("[yellow]暂无更新提醒[/yellow]")
        return
    console.print("[bold]📺 更新提醒[/bold]\n")
    for r in reminders:
        console.print(f"  {r['message']}")


def _print_translation_list(items: list[dict]) -> None:
    if not items:
        console.print("[green]✓ 无待翻译条目[/green]")
        return
    table = Table(title="🌐 待翻译列表")
    table.add_column("片名", style="cyan")
    table.add_column("年份")
    table.add_column("原因", style="red")

    for item in items:
        name = item["title_cn"] or item["title_en"] or "-"
        table.add_row(name, str(item.get("year") or "-"), item.get("reason", ""))
    console.print(table)


def _print_ranking(ranking: list[dict]) -> None:
    if not ranking:
        console.print("[yellow]暂无评分数据[/yellow]")
        return
    console.print("[bold]🏆 推荐榜单[/bold]\n")
    for r in ranking:
        name = r["title_cn"] or r["title_en"]
        year = f" ({r['year']})" if r.get("year") else ""
        rating = r.get("rating", "N/A")
        genre = r.get("genre", "")
        console.print(f"  {r['rank']}. {name}{year} ⭐{rating} {genre}")


def _type_short(st: ShowType) -> str:
    return {
        ShowType.MOVIE: "电影",
        ShowType.TV: "剧集",
        ShowType.VARIETY: "综艺",
        ShowType.ANIME: "动漫",
        ShowType.UNKNOWN: "—",
    }.get(st, "—")


def _status_short(st: ShowStatus) -> str:
    return {
        ShowStatus.AIRING: "播出中",
        ShowStatus.UPCOMING: "待播",
        ShowStatus.ENDED: "完结",
        ShowStatus.CANCELLED: "取消",
        ShowStatus.UNKNOWN: "—",
    }.get(st, "—")
