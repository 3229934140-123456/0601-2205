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
    export_weekly_report,
    export_calendar,
    export_subscription_reminders,
    apply_supplement,
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


@app.command("weekly", help="导出周报（支持字幕组/观影社群/个人三种模板）")
def weekly_cmd(
    output: Path = typer.Argument(..., help="输出文件路径"),
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
    template: str = typer.Option("community", "--template", help="周报模板：subteam（字幕组）/ community（观影社群）/ personal（个人追剧）"),
    fmt: str = typer.Option("markdown", "--format", help="输出格式：markdown / csv / json"),
):
    database = ShowDatabase(_db_path(db))
    if template not in ("subteam", "community", "personal"):
        console.print(f"[red]未知模板: {template}[/red]")
        raise typer.Exit(1)
    export_weekly_report(database, output, template, fmt)
    console.print(f"[green]✓ 周报已导出到 {output}（模板：{template}）[/green]")


@app.command("calendar", help="导出日历文件（iCal 格式，可导入系统日历）")
def calendar_cmd(
    output: Path = typer.Argument(..., help="输出 .ics 文件路径"),
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
):
    database = ShowDatabase(_db_path(db))
    export_calendar(database, output)
    console.print(f"[green]✓ 日历已导出到 {output}[/green]")
    console.print(f"[yellow]提示：可双击 .ics 文件导入系统日历，包含上映/首播/下一集更新等事件[/yellow]")


@app.command("remind", help="订阅式提醒导出（今天/未来7天/未来30天三档）")
def remind_cmd(
    output: Path = typer.Argument(..., help="输出文件路径"),
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
    fmt: str = typer.Option("markdown", "--format", help="输出格式：markdown / csv / json"),
    platform: Optional[str] = typer.Option(None, "--platform", help="按平台筛选"),
    show_type: Optional[str] = typer.Option(None, "--type", help="按类型筛选：movie / tv / variety / anime"),
    assignee: Optional[str] = typer.Option(None, "--assignee", help="按负责人筛选"),
    only_translated: bool = typer.Option(False, "--only-translated", help="只显示已翻译的"),
    compact: bool = typer.Option(False, "--compact", help="精简版（适合机器人/日历订阅）"),
):
    database = ShowDatabase(_db_path(db))
    export_subscription_reminders(
        database, output, fmt,
        platform=platform, show_type=show_type,
        assignee=assignee, only_translated=only_translated,
        compact=compact,
    )
    console.print(f"[green]✓ 订阅提醒已导出到 {output}[/green]")
    from .exporter import generate_subscription_reminders
    data = generate_subscription_reminders(
        database, platform=platform, show_type=show_type,
        assignee=assignee, only_translated=only_translated,
    )
    for key in ["today", "week", "month"]:
        sec = data["sections"][key]
        if sec["total"] > 0:
            console.print(f"  {sec['label']}: 更新 {sec['updates_count']} / 新上线 {sec['new_releases_count']}")


@app.command("supplement", help="从本地补充表补全资料（TMDB没补到的平台/导演/主演等）")
def supplement_cmd(
    supplement_file: Path = typer.Argument(..., help="补充表文件路径（CSV/Excel）"),
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
    mode: str = typer.Option("fill", "--mode", help="更新模式：fill（只补缺失）/ overwrite（全部覆盖）/ check（仅检查冲突）"),
):
    database = ShowDatabase(_db_path(db))
    if not supplement_file.exists():
        console.print(f"[red]补充表不存在: {supplement_file}[/red]")
        raise typer.Exit(1)

    if mode not in ("fill", "overwrite", "check"):
        console.print(f"[red]未知模式: {mode}，请使用 fill / overwrite / check[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]正在从补充表 {supplement_file} 补全资料（模式：{mode}）...[/cyan]")
    stats = apply_supplement(database, supplement_file, mode=mode)

    if mode == "check":
        console.print(f"[cyan]✓ 检查完成，未修改数据[/cyan]")
    else:
        console.print(f"[green]✓ 补充完成[/green]")
    console.print(f"  匹配到: {stats['matched']} 条")
    console.print(f"  字段更新: {stats['fields_updated']} 处")
    if stats["platform_updated"]:
        console.print(f"    平台: {stats['platform_updated']} 处")
    if stats["director_updated"]:
        console.print(f"    导演: {stats['director_updated']} 处")
    if stats["cast_updated"]:
        console.print(f"    主演: {stats['cast_updated']} 处")
    if stats["genre_updated"]:
        console.print(f"    类型: {stats['genre_updated']} 处")
    if stats["fields_skipped"]:
        console.print(f"[yellow]  冲突跳过: {stats['fields_skipped']} 处[/yellow]")
    if stats["not_found"]:
        console.print(f"[yellow]  未匹配到: {stats['not_found']} 条[/yellow]")
    if stats["conflicts"]:
        console.print()
        console.print(f"[yellow]⚠️ 发现 {len(stats['conflicts'])} 处字段冲突：[/yellow]")
        conflict_table = Table(title="字段冲突列表")
        conflict_table.add_column("片名", style="cyan")
        conflict_table.add_column("字段")
        conflict_table.add_column("现有值", style="green")
        conflict_table.add_column("补充值", style="yellow")
        for c in stats["conflicts"][:20]:
            conflict_table.add_row(c["show_title"], c["field"], c["old_value"], c["new_value"])
        console.print(conflict_table)
        if len(stats["conflicts"]) > 20:
            console.print(f"[dim]... 还有 {len(stats['conflicts']) - 20} 处冲突，请使用 --mode check 查看完整列表[/dim]")
        console.print()
        console.print("[yellow]提示：[/yellow]")
        console.print("  --mode fill      只补缺失（默认）")
        console.print("  --mode overwrite  全部覆盖补充表的值")
        console.print("  --mode check      仅检查冲突不修改")


@app.command("progress", help="管理追剧进度：标记已看集数、翻译状态、负责人")
def progress_cmd(
    title: str = typer.Argument(..., help="片名（中文名或英文名）"),
    db: Optional[str] = typer.Option(None, "--db", help="数据库文件路径"),
    watched_season: Optional[int] = typer.Option(None, "--watched-season", "--ws", help="已看季数"),
    watched_episode: Optional[int] = typer.Option(None, "--watched-episode", "--we", help="已看集数"),
    translated: Optional[str] = typer.Option(None, "--translated", help="翻译状态：yes / no"),
    translator: Optional[str] = typer.Option(None, "--translator", help="译者"),
    assignee: Optional[str] = typer.Option(None, "--assignee", help="负责人"),
    show: bool = typer.Option(False, "--show", help="仅显示当前进度，不修改"),
):
    database = ShowDatabase(_db_path(db))
    matched = None
    title_lower = title.lower()
    for s in database.shows:
        if (s.title_cn and s.title_cn.lower() == title_lower) or \
           (s.title_en and s.title_en.lower() == title_lower):
            matched = s
            break
    if not matched:
        for s in database.shows:
            if (s.title_cn and title_lower in s.title_cn.lower()) or \
               (s.title_en and title_lower in s.title_en.lower()):
                matched = s
                break

    if not matched:
        console.print(f"[red]未找到条目: {title}[/red]")
        raise typer.Exit(1)

    display_title = matched.title_cn or matched.title_en

    if show:
        console.print(f"[cyan]📺 {display_title} 的进度信息：[/cyan]")
        if matched.watched_season or matched.watched_episode:
            ws = matched.watched_season or 0
            we = matched.watched_episode or 0
            console.print(f"  观看进度: S{ws:02d}E{we:02d}")
        else:
            console.print(f"  观看进度: 未标记")
        console.print(f"  翻译状态: {'已翻译' if matched.translated else '未翻译'}")
        if matched.translator:
            console.print(f"  译    者: {matched.translator}")
        if matched.assignee:
            console.print(f"  负 责 人: {matched.assignee}")
        return

    updated_fields = []
    if watched_season is not None:
        matched.watched_season = watched_season
        updated_fields.append(f"已看季={watched_season}")
    if watched_episode is not None:
        matched.watched_episode = watched_episode
        updated_fields.append(f"已看集={watched_episode}")
    if translated is not None:
        translated_bool = translated.lower() in ("yes", "true", "1", "是", "已翻译")
        matched.translated = translated_bool
        updated_fields.append(f"翻译={'已翻译' if translated_bool else '未翻译'}")
    if translator is not None:
        matched.translator = translator if translator.lower() != "none" else ""
        updated_fields.append(f"译者={matched.translator or '清空'}")
    if assignee is not None:
        matched.assignee = assignee if assignee.lower() != "none" else ""
        updated_fields.append(f"负责人={matched.assignee or '清空'}")

    if not updated_fields:
        console.print("[yellow]未指定任何要修改的字段，请使用 --ws/--we/--translated/--translator/--assignee[/yellow]")
        console.print("[yellow]或使用 --show 查看当前进度[/yellow]")
        raise typer.Exit(1)

    database.save()
    console.print(f"[green]✓ {display_title} 进度已更新[/green]")
    for f in updated_fields:
        console.print(f"  {f}")


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
    table.add_column("中文名", style="cyan", max_width=18)
    table.add_column("英文名", style="cyan", max_width=20)
    table.add_column("上线日期", width=12)
    table.add_column("下一集", width=12)
    table.add_column("类型", width=5)
    table.add_column("状态", width=8)
    table.add_column("已看", width=9)
    table.add_column("翻译", width=6)
    table.add_column("负责人", max_width=10)
    table.add_column("平台", max_width=12)
    table.add_column("评分", width=5)

    for show in shows:
        name = show.title_cn or "-"
        en = show.title_en or "-"
        release_date = show.primary_date().isoformat() if show.primary_date() else "-"
        next_date = show.next_episode_date.isoformat() if show.next_episode_date else "-"
        stype = _type_short(show.show_type)
        st = _status_short(show.status)
        watched = ""
        if show.watched_season:
            watched += f"S{show.watched_season:02d}"
        if show.watched_episode:
            watched += f"E{show.watched_episode:02d}"
        if not watched:
            watched = "-"
        translated_str = "✓" if show.translated else "-"
        assignee = show.assignee or "-"
        platform = show.platform or "-"
        rating = str(show.rating) if show.rating else "-"
        missing = show.missing_fields()
        if missing:
            name = f"{name} ⚠️"

        table.add_row(name, en, release_date, next_date, stype, st, watched, translated_str, assignee, platform, rating)

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
