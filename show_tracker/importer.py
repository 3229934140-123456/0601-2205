from __future__ import annotations

from pathlib import Path

import pandas as pd

from .models import Show, ShowDatabase, parse_raw_title


def import_from_csv(path: Path, db: ShowDatabase, title_col: str = "title", merge: bool = False) -> list[Show]:
    df = pd.read_csv(path, dtype=str).fillna("")
    return _import_dataframe(df, db, title_col, merge)


def import_from_excel(path: Path, db: ShowDatabase, title_col: str = "title", merge: bool = False) -> list[Show]:
    df = pd.read_excel(path, dtype=str).fillna("")
    return _import_dataframe(df, db, title_col, merge)


def import_from_text(path: Path, db: ShowDatabase, merge: bool = False) -> list[Show]:
    lines = path.read_text(encoding="utf-8").splitlines()
    imported: list[Show] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        show = parse_raw_title(line)
        if merge:
            show = db.merge(show)
        else:
            if not db.add(show):
                continue
        imported.append(show)
    return imported


def _import_dataframe(df: pd.DataFrame, db: ShowDatabase, title_col: str, merge: bool) -> list[Show]:
    col_map = {c.lower(): c for c in df.columns}
    tc = col_map.get(title_col.lower(), title_col)
    imported: list[Show] = []

    for _, row in df.iterrows():
        raw_title = str(row.get(tc, "")).strip()
        if not raw_title:
            continue
        show = parse_raw_title(raw_title)
        _fill_from_row(show, row, col_map)
        if merge:
            show = db.merge(show)
        else:
            if not db.add(show):
                continue
        imported.append(show)
    return imported


def _fill_from_row(show: Show, row: pd.Series, col_map: dict[str, str]) -> None:
    field_map = {
        "title_cn": "title_cn",
        "title_en": "title_en",
        "year": "year",
        "season": "season",
        "episode": "episode",
        "director": "director",
        "cast": "cast",
        "genre": "genre",
        "duration": "duration",
        "platform": "platform",
        "poster_url": "poster_url",
        "notes": "notes",
    }
    from .models import ShowType, ShowStatus, _STATUS_MAP, _TYPE_MAP

    for attr, col_name in field_map.items():
        mapped = col_map.get(col_name.lower(), col_name)
        val = row.get(mapped, "")
        if isinstance(val, str):
            val = val.strip()
        if not val:
            continue
        if attr == "year":
            try:
                setattr(show, attr, int(val))
            except (ValueError, TypeError):
                pass
        elif attr == "season":
            try:
                setattr(show, attr, int(val))
            except (ValueError, TypeError):
                pass
        elif attr == "episode":
            try:
                setattr(show, attr, int(val))
            except (ValueError, TypeError):
                pass
        else:
            setattr(show, attr, val)

    status_col = col_map.get("status", "status")
    status_val = str(row.get(status_col, "")).strip()
    if status_val:
        for kw, st in _STATUS_MAP.items():
            if kw in status_val:
                show.status = st
                break

    type_col = col_map.get("show_type", "show_type")
    type_val = str(row.get(type_col, "")).strip().lower()
    if type_val:
        for kw, st in _TYPE_MAP.items():
            if kw.lower() == type_val or kw in type_val:
                show.show_type = st
                break
