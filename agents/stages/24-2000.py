# consolidate_data.py
# -*- coding: utf-8 -*-
"""
Консолидация телеметрии и лабораторных анализов.

Формирует:
  1) consolidated_full.csv — вся телеметрия (с интерполяцией) + LIMS
     там, где есть проба в окне ±1ч. Строки не выбрасываются.
  2) consolidated_lab.csv  — только строки с лабораторным замером серы.
"""

from __future__ import annotations

import re
import numpy as np
import pandas as pd
from pathlib import Path

# ======================================================================
# 0. КОНФИГ
# ======================================================================
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR     = PROJECT_ROOT / "resources" / "Neftcode_2.0"

TELEMETRY_FILE = DATA_DIR / "data/242000_tags.csv"
LAB_FILE       = DATA_DIR / "ЛИМСы 01.01.2023 - н.в_3 (1).xlsx"
OUT_FULL       = DATA_DIR / "consolidated_full.csv"
OUT_LAB        = DATA_DIR / "consolidated_lab.csv"

LAB_SHEET = 0
LAB_MATCH_WINDOW_HOURS = 1.0
TARGET_SULFUR_HINT = "Mass.Sulfur"   # или "Mg.Sulfur"

SEP = ","

USED_TAGS = [
    "F1","F2","P3","W4","T5","T6","W7","P8","P9","W10","T11","T12",
    "P13","F14","F15","T16","F17","T18","F19","Q20","Q21","F22","T23",
    "P24","F25","F26",
]

UNIT_MARKERS = (
    "°С", "°C", "кг/м3", "кг/м³", "% масс", "% масс.", "% об", "% об.",
    "мг/кг", "ppm", "ед.цет", "ед.цет.ч", "МПа", "нм3", "нм³",
    "м3/ч", "м³/ч", "т/ч",
)

RU_MONTHS = {
    "янв": 1,  "январь": 1,  "января": 1,
    "фев": 2,  "февр": 2,   "февраль": 2, "февраля": 2,
    "мар": 3,  "март": 3,   "марта": 3,
    "апр": 4,  "апрель": 4, "апреля": 4,
    "май": 5,  "мая": 5,
    "июн": 6,  "июнь": 6,   "июня": 6,
    "июл": 7,  "июль": 7,   "июля": 7,
    "авг": 8,  "август": 8, "августа": 8,
    "сен": 9,  "сент": 9,   "сентябрь": 9, "сентября": 9,
    "окт": 10, "октябрь": 10, "октября": 10,
    "ноя": 11, "нояб": 11,  "ноябрь": 11, "ноября": 11,
    "дек": 12, "декабрь": 12, "декабря": 12,
}

_RU_MONTH_RE = re.compile(
    r"^\s*(\d{1,2})[-\.\s\/]+([А-Яа-яЁё]+)[-\.\s\/]+(\d{2,4})"
    r"(?:[\sT]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*$"
)


# ======================================================================
# 1. УНИВЕРСАЛЬНЫЙ ПАРСЕР ДАТ
# ======================================================================
def _parse_one_date(v) -> pd.Timestamp:
    """Парсит одну ячейку в pd.Timestamp. Возвращает pd.NaT, если не удалось."""
    if v is None:
        return pd.NaT
    if isinstance(v, pd.Timestamp):
        return v
    if hasattr(v, "year") and hasattr(v, "month"):   # datetime/date
        return pd.Timestamp(v)

    # NaN
    try:
        if pd.isna(v):
            return pd.NaT
    except (TypeError, ValueError):
        pass

    # числа: excel serial или unix
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        f = float(v)
        # excel serial date (дни от 1899-12-30)
        if 20000 <= f <= 60000:
            return pd.Timestamp("1899-12-30") + pd.to_timedelta(f, unit="D")
        # unix
        if 1e8 <= f < 1e11:
            return pd.Timestamp(f, unit="s")
        if 1e11 <= f < 1e14:
            return pd.Timestamp(f, unit="ms")
        if 1e14 <= f < 1e17:
            return pd.Timestamp(f, unit="us")
        if f >= 1e17:
            return pd.Timestamp(f, unit="ns")
        return pd.NaT

    # строки
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "nat", "none"):
        return pd.NaT

    # русские месяцы: "15-янв-26 10:00:00"
    m = _RU_MONTH_RE.match(s)
    if m:
        day, mon_name, year, hh, mm, ss = m.groups()
        mon = RU_MONTHS.get(mon_name.lower()[:4]) or RU_MONTHS.get(mon_name.lower()[:3])
        if mon is None:
            return pd.NaT
        y = int(year)
        if y < 100:
            y += 2000 if y < 70 else 1900
        try:
            return pd.Timestamp(year=y, month=mon, day=int(day),
                                hour=int(hh) if hh else 0,
                                minute=int(mm) if mm else 0,
                                second=int(ss) if ss else 0)
        except ValueError:
            return pd.NaT

    # ISO и всё остальное — пробуем через pandas
    try:
        return pd.to_datetime(s, dayfirst=True)
    except Exception:
        pass
    try:
        return pd.to_datetime(s, dayfirst=False)
    except Exception:
        return pd.NaT


def parse_time_column(series: pd.Series) -> pd.Series:
    """Применяет _parse_one_date к каждой ячейке."""
    return series.map(_parse_one_date)


# ======================================================================
# 2. ТЕЛЕМЕТРИЯ
# ======================================================================
def load_telemetry(path: Path) -> pd.DataFrame:
    # utf-8-sig — убирает BOM в имени первой колонки
    df = pd.read_csv(path, sep=SEP, encoding="utf-8-sig")
    df.columns = [str(c).lstrip("\ufeff").strip() for c in df.columns]

    time_col = None
    for c in df.columns:
        if c.lower() in ("timestamp", "time", "datetime", "дата", "время"):
            time_col = c
            break
    if time_col is None:
        time_col = df.columns[0]

    df = df.rename(columns={time_col: "timestamp"})
    df["timestamp"] = parse_time_column(df["timestamp"])
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    for c in df.columns:
        if c != "timestamp":
            df[c] = pd.to_numeric(df[c], errors="coerce")

    keep = ["timestamp"] + [t for t in USED_TAGS if t in df.columns]
    return df[keep].reset_index(drop=True)


# ======================================================================
# 3. ЛАБОРАТОРИЯ (Excel)
# ======================================================================
def _forward_fill_merged(row: list) -> list:
    out, last = [], None
    for v in row:
        if pd.isna(v) or (isinstance(v, str) and v.strip() == ""):
            out.append(last)
        else:
            last = v
            out.append(v)
    return out


def _looks_like_units_row(row) -> bool:
    return any(isinstance(v, str) and any(m in v for m in UNIT_MARKERS)
               for v in row)


def _is_readable_tag(s) -> bool:
    if not isinstance(s, str):
        return False
    s = s.strip()
    if not s:
        return False
    return re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9 _\-\.\(\)]{1,80}", s) is not None


def _clean_tag(s: str) -> str:
    s = str(s).strip()
    s = re.sub(r"[^A-Za-zА-Яа-яЁё0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:40]


def _normalize_lab_name(name: str) -> str:
    name = str(name).strip()
    name = re.sub(r"\s+", "", name)
    if name == "" or name.lower() == "nan":
        return ""
    return name if name.startswith("LIMS.") else f"LIMS.{name}"


def _find_header_rows(raw: pd.DataFrame) -> dict:
    """Ищет строку единиц измерения и первую строку с датой."""
    n = min(30, len(raw))

    unit_row = None
    for i in range(n):
        if _looks_like_units_row(raw.iloc[i].tolist()):
            unit_row = i
            break
    if unit_row is None:
        raise ValueError(
            "Не нашёл строку с единицами измерения (°С, кг/м3, ...). "
            "Проверьте первые 30 строк файла."
        )

    param_row = max(unit_row - 1, 0)

    # ищем первую строку, где хотя бы в одной из первых 5 колонок дата
    data_row = None
    for i in range(unit_row + 1, len(raw)):
        for col in range(min(5, raw.shape[1])):
            ts = _parse_one_date(raw.iat[i, col])
            if pd.notna(ts):
                data_row = i
                break
        if data_row is not None:
            break

    if data_row is None:
        raise ValueError("Не нашёл первую строку с датой.")

    return {
        "param_row": param_row,
        "unit_row":  unit_row,
        "data_row":  data_row,
        "skipped_rows": list(range(unit_row + 1, data_row)),
    }


def _detect_time_column(data: pd.DataFrame) -> int:
    """Возвращает индекс колонки, где больше всего дат."""
    best_idx, best_cnt = 0, -1
    for i in range(min(5, data.shape[1])):
        parsed = data.iloc[:, i].map(_parse_one_date)
        cnt = parsed.notna().sum()
        if cnt > best_cnt:
            best_idx, best_cnt = i, cnt
    return best_idx


def _build_column_names(param_values, group_values):
    names = {}
    used = set()
    for i in range(len(param_values)):
        base = _normalize_lab_name(param_values[i])
        if base == "":
            base = f"LIMS.col{i}"

        grp = group_values[i] if i < len(group_values) else None
        if _is_readable_tag(grp):
            grp_tag = _clean_tag(grp)
            if grp_tag:
                base = f"{base}__{grp_tag}"

        name = base
        k = 0
        while name in used:
            k += 1
            name = f"{base}_{k}"
        used.add(name)
        names[i] = name
    return names


def _read_one_sheet(path: Path, sheet) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=None, dtype=object)

    info = _find_header_rows(raw)
    print(f"[sheet={sheet!r}] param_row={info['param_row']}, "
          f"unit_row={info['unit_row']}, data_row={info['data_row']}, "
          f"skipped={info['skipped_rows']}")

    # параметры и группы (строка 0 — объединённая шапка)
    param_values = _forward_fill_merged(raw.iloc[info["param_row"]].tolist())
    group_values = _forward_fill_merged(raw.iloc[0].tolist())

    data = raw.iloc[info["data_row"]:].reset_index(drop=True)
    data.columns = range(data.shape[1])

    # --- определяем колонку времени автоматически ---
    time_idx = _detect_time_column(data)
    print(f"[sheet={sheet!r}] time column index = {time_idx}")

    data = data.rename(columns={time_idx: "timestamp"})
    data["timestamp"] = parse_time_column(data["timestamp"])
    data = data.dropna(subset=["timestamp"]).sort_values("timestamp")

    # --- имена колонок (кроме time_idx) ---
    # переиндексируем param_values так, чтобы индексы совпадали с data
    param_by_col = {i: v for i, v in enumerate(param_values)}
    group_by_col = {i: v for i, v in enumerate(group_values)}

    new_names = {}
    used = set()
    for col in data.columns:
        if col == "timestamp":
            continue
        base = _normalize_lab_name(param_by_col.get(col, ""))
        if base == "":
            base = f"LIMS.col{col}"

        grp = group_by_col.get(col)
        if _is_readable_tag(grp):
            grp_tag = _clean_tag(grp)
            if grp_tag:
                base = f"{base}__{grp_tag}"

        name = base
        k = 0
        while name in used:
            k += 1
            name = f"{base}_{k}"
        used.add(name)
        new_names[col] = name

    data = data.rename(columns=new_names)

    lab_cols = [c for c in data.columns if c.startswith("LIMS.")]
    for c in lab_cols:
        col = data[c]
        if isinstance(col, pd.DataFrame):
            col = col.apply(pd.to_numeric, errors="coerce").mean(axis=1)
        else:
            col = pd.to_numeric(col, errors="coerce")
        data[c] = col

    data = data.loc[:, ~data.columns.duplicated(keep="first")]
    return data[["timestamp"] + lab_cols].reset_index(drop=True)


def load_lab(path: Path, sheet=LAB_SHEET) -> pd.DataFrame:
    xls = pd.ExcelFile(path)
    if sheet is None:
        sheets = xls.sheet_names
    elif isinstance(sheet, (list, tuple)):
        sheets = list(sheet)
    else:
        sheets = [sheet]

    frames = []
    for s in sheets:
        df = _read_one_sheet(path, s)
        if df.empty:
            continue
        sheet_tag = re.sub(r"\W+", "_", str(s)).strip("_") or "sheet"
        df = df.rename(columns={
            c: f"{c}__sheet_{sheet_tag}"
            for c in df.columns if c.startswith("LIMS.")
        })
        frames.append(df)

    if not frames:
        raise ValueError("Не удалось прочитать ни одного листа Excel")

    lab = frames[0]
    for nxt in frames[1:]:
        lab = pd.merge(lab, nxt, on="timestamp", how="outer")
    return lab.sort_values("timestamp").reset_index(drop=True)


# ======================================================================
# 4. ИНТЕРПОЛЯЦИЯ ТЕЛЕМЕТРИИ
# ======================================================================
def interpolate_telemetry(tele: pd.DataFrame,
                          target_index: pd.DatetimeIndex) -> pd.DataFrame:
    t = tele.set_index("timestamp").sort_index()
    target_index = pd.DatetimeIndex(target_index).sort_values()

    combined = t.reindex(t.index.union(target_index))
    combined = combined.interpolate(method="time", limit_direction="both")

    out = combined.reindex(target_index)
    out.index.name = "timestamp"
    return out.reset_index()


# ======================================================================
# 5. СОПОСТАВЛЕНИЕ LIMS ↔ ТЕЛЕМЕТРИЯ
# ======================================================================
def match_lab_to_telemetry(lab: pd.DataFrame,
                           tele: pd.DataFrame,
                           window_hours: float = LAB_MATCH_WINDOW_HOURS
                           ) -> pd.DataFrame:
    lab_cols = [c for c in lab.columns if c.startswith("LIMS.")]
    half = pd.Timedelta(hours=window_hours)

    lab_sorted = lab.sort_values("timestamp").reset_index(drop=True)

    rows = []
    for ts in tele["timestamp"]:
        lo, hi = ts - half, ts + half
        mask = (lab_sorted["timestamp"] >= lo) & (lab_sorted["timestamp"] <= hi)
        sub = lab_sorted.loc[mask, lab_cols]
        row = (sub.mean(numeric_only=True).to_dict()
               if not sub.empty else {c: np.nan for c in lab_cols})
        row["timestamp"] = ts
        rows.append(row)

    return pd.DataFrame(rows)[["timestamp"] + lab_cols]


# ======================================================================
# 6. СБОРКА ДАТАСЕТОВ
# ======================================================================
def build_full_dataset(tele: pd.DataFrame, lab: pd.DataFrame) -> pd.DataFrame:
    tele_interp = interpolate_telemetry(tele, tele["timestamp"])
    lab_matched = match_lab_to_telemetry(lab, tele_interp)
    out = pd.merge(tele_interp, lab_matched, on="timestamp", how="left")
    return out.sort_values("timestamp").reset_index(drop=True)


def build_lab_dataset(full: pd.DataFrame,
                      lab_hint: str = TARGET_SULFUR_HINT) -> pd.DataFrame:
    sulfur_cols = [c for c in full.columns
                   if c.startswith("LIMS.") and lab_hint in c]
    if not sulfur_cols:
        raise KeyError(
            f"Не нашёл LIMS-колонок с '{lab_hint}'. "
            f"Доступные LIMS: "
            f"{[c for c in full.columns if c.startswith('LIMS.')]}"
        )
    has_lab = full[sulfur_cols].notna().any(axis=1)
    return full.loc[has_lab].reset_index(drop=True)


# ======================================================================
# 7. MAIN
# ======================================================================
def main():
    print("-> Чтение телеметрии...")
    tele = load_telemetry(TELEMETRY_FILE)
    print(f"   строк: {len(tele)}, колонок: {tele.shape[1]}")
    print(f"   период: {tele['timestamp'].min()} - {tele['timestamp'].max()}")
    print(f"   NaT: {tele['timestamp'].isna().sum()}")

    print("-> Чтение лаборатории...")
    lab = load_lab(LAB_FILE, sheet=LAB_SHEET)
    print(f"   проб: {len(lab)}, LIMS-параметров: {lab.shape[1] - 1}")
    print(f"   период: {lab['timestamp'].min()} - {lab['timestamp'].max()}")
    print(f"   NaT: {lab['timestamp'].isna().sum()}")
    print(f"   первые 5 дат: {lab['timestamp'].head().tolist()}")

    print("-> Полный датасет (телеметрия + интерполяция + LIMS)...")
    full = build_full_dataset(tele, lab)
    full.to_csv(OUT_FULL, index=False, encoding="utf-8-sig")
    print(f"   сохранено: {OUT_FULL} ({full.shape})")
    print(f"   период: {full['timestamp'].min()} - {full['timestamp'].max()}")

    print("-> Датасет с лабораторными замерами серы...")
    lab_ds = build_lab_dataset(full)
    lab_ds.to_csv(OUT_LAB, index=False, encoding="utf-8-sig")
    print(f"   сохранено: {OUT_LAB} ({lab_ds.shape})")

    sulfur_cols = [c for c in full.columns
                   if c.startswith("LIMS.") and "Sulfur" in c]
    for c in sulfur_cols:
        print(f"   {c}: notna = {full[c].notna().sum()}")


if __name__ == "__main__":
    main()