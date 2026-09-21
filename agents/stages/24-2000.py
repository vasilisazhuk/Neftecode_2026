# consolidate_data.py
# -*- coding: utf-8 -*-
"""
Консолидация телеметрии и лабораторных анализов.

Формирует два датасета:

1) consolidated_full.csv
   Все теги телеметрии, интерполированные по времени.
   Для каждой метки времени, где нет прямого замера, значение берётся
   как среднее между двумя ближайшими по времени метками телеметрии
   (линейная интерполяция). Сохраняются ВСЕ строки, включая те,
   где лабораторных замеров нет (LIMS-колонки = NaN).

2) consolidated_lab.csv
   То же, но остаются только строки, где есть хотя бы один
   лабораторный замер в окне ±1 час от метки времени.
   Лабораторные значения усредняются по всем пробам в окне.
"""

from __future__ import annotations

import re
import numpy as np
import pandas as pd
from pathlib import Path

# ----------------------------------------------------------------------
# 0. КОНФИГ
# ----------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR     = PROJECT_ROOT / "resources" / "Neftcode_2.0"

TELEMETRY_FILE = DATA_DIR / "data/242000_tags.csv"
LAB_FILE       = DATA_DIR / "ЛИМСы 01.01.2023 - н.в_3 (1).xlsx"
OUT_FULL       = DATA_DIR / "consolidated_full.csv"
OUT_LAB        = DATA_DIR / "consolidated_lab.csv"

LAB_SHEET = 0

# Окно для поиска лабораторного замера вокруг метки времени
LAB_MATCH_WINDOW_HOURS = 1.0

SEP = ","

TARGET_LAB_HINTS = ("Mass.Sulfur", "Mg.Sulfur")   # приоритетные цели

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


# ----------------------------------------------------------------------
# 1. ТЕЛЕМЕТРИЯ
# ----------------------------------------------------------------------
def load_telemetry(path: Path) -> pd.DataFrame:
    """
    Читает телеметрию, приводит время к datetime, оставляет
    только USED_TAGS. Никаких dropna — null-значения сохраняются.
    """
    df = pd.read_csv(path, sep=SEP, encoding="utf-8")
    df.columns = [str(c).strip() for c in df.columns]

    time_col = None
    for c in df.columns:
        if c.lower() in ("timestamp", "time", "datetime", "дата", "время"):
            time_col = c
            break
    if time_col is None:
        time_col = df.columns[0]

    df = df.rename(columns={time_col: "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce",
                                     dayfirst=True)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    for c in df.columns:
        if c != "timestamp":
            df[c] = pd.to_numeric(df[c], errors="coerce")

    keep = ["timestamp"] + [t for t in USED_TAGS if t in df.columns]
    df = df[keep].reset_index(drop=True)
    return df


# ----------------------------------------------------------------------
# 2. ЛАБОРАТОРИЯ
# ----------------------------------------------------------------------

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
    r"(\d{1,2})[-\.\s]+([А-Яа-яЁё]+)[-\.\s]+(\d{2,4})"
    r"(?:[\sT]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?"
)


def _parse_lab_time(series: pd.Series) -> pd.Series:
    """Парсит колонку времени из Excel в pd.Timestamp.
    Поддерживает:
      - '21-янв-26 10:00:00' (русские месяцы)
      - '2023-01-21 10:00:00' (ISO)
      - '21.01.2023 10:00' (числовой)
      - Excel serial date (числа 20000..60000)
      - unix-время (числа > 1e8)
      - datetime64
    """
    s = series.copy()

    if pd.api.types.is_datetime64_any_dtype(s):
        return s

    # --- числа: excel serial / unix ---
    if pd.api.types.is_numeric_dtype(s):
        num = pd.to_numeric(s, errors="coerce")
        med = num.dropna().median() if num.notna().any() else None
        if med is not None:
            if 20000 <= med <= 60000:
                origin = pd.Timestamp("1899-12-30")
                return origin + pd.to_timedelta(num, unit="D")
            if 1e8  <= med < 1e11: return pd.to_datetime(num, unit="s",  errors="coerce")
            if 1e11 <= med < 1e14: return pd.to_datetime(num, unit="ms", errors="coerce")
            if 1e14 <= med < 1e17: return pd.to_datetime(num, unit="us", errors="coerce")
            if med >= 1e17:        return pd.to_datetime(num, unit="ns", errors="coerce")
        return pd.to_datetime(num, errors="coerce")

    # --- строки ---
    s_str = s.astype(str).str.strip()

    # быстрый тест: пробуем стандартный парсер
    fast = pd.to_datetime(s_str, errors="coerce", dayfirst=True)
    if fast.notna().sum() >= 0.9 * s_str.notna().sum():
        return fast

    # --- русские месяцы ---
    def parse_one(v: str):
        if not isinstance(v, str) or v.strip() == "" or v.lower() == "nan":
            return pd.NaT

        m = _RU_MONTH_RE.search(v.strip().lower())
        if not m:
            # не подошло — отдаём pandas
            try:
                return pd.to_datetime(v, errors="raise", dayfirst=True)
            except Exception:
                return pd.NaT

        day, mon_name, year = m.group(1), m.group(2), m.group(3)
        mon = RU_MONTHS.get(mon_name[:3]) or RU_MONTHS.get(mon_name)
        if mon is None:
            return pd.NaT

        # год: 2 цифры -> 20xx
        year = int(year)
        if year < 100:
            year += 2000

        hour   = int(m.group(4)) if m.group(4) else 0
        minute = int(m.group(5)) if m.group(5) else 0
        second = int(m.group(6)) if m.group(6) else 0

        try:
            return pd.Timestamp(year=year, month=mon, day=int(day),
                                hour=hour, minute=minute, second=second)
        except ValueError:
            return pd.NaT

    return s_str.map(parse_one)

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
    return any(
        isinstance(v, str) and any(m in v for m in UNIT_MARKERS)
        for v in row
    )


def _is_datetime_value(v) -> bool:
    if pd.isna(v):
        return False
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "year"):
        return True
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                    "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
                    "%Y-%m-%d", "%d.%m.%Y"):
            try:
                pd.to_datetime(v.strip(), format=fmt)
                return True
            except (ValueError, TypeError):
                continue
    if isinstance(v, (int, float)) and 20000 < v < 60000:
        return True   # excel serial date
    return False


def _find_header_rows(raw: pd.DataFrame) -> dict:
    n = min(20, len(raw))
    unit_row = None
    for i in range(n):
        if _looks_like_units_row(raw.iloc[i].tolist()):
            unit_row = i
            break
    if unit_row is None:
        raise ValueError(
            "Не нашёл строку с единицами измерения (°С, кг/м3, ...). "
            "Проверьте первые 20 строк файла."
        )

    param_row = max(unit_row - 1, 0)

    data_row = None
    for i in range(unit_row + 1, len(raw)):
        if _is_datetime_value(raw.iat[i, 0]):
            data_row = i
            break
    if data_row is None:
        raise ValueError("Не нашёл первую строку с датой.")

    return {
        "param_row": param_row,
        "unit_row":  unit_row,
        "data_row":  data_row,
        "skipped_rows": list(range(unit_row + 1, data_row)),
    }


def _build_column_names(param_values, group_values):
    names = {0: "timestamp"}
    used = set()
    for i in range(1, len(param_values)):
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

    param_values = _forward_fill_merged(raw.iloc[info["param_row"]].tolist())
    group_values = _forward_fill_merged(raw.iloc[0].tolist())

    data = raw.iloc[info["data_row"]:].reset_index(drop=True)
    data.columns = range(data.shape[1])

    data = data.rename(columns={0: "timestamp"})
    #data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce",
    #                                   dayfirst=True)
    data["timestamp"] = _parse_lab_time(data["timestamp"])
    data = data.dropna(subset=["timestamp"]).sort_values("timestamp")

    data = data.rename(columns=_build_column_names(param_values, group_values))

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


# ----------------------------------------------------------------------
# 3. ИНТЕРПОЛЯЦИЯ ТЕЛЕМЕТРИИ ПО ВРЕМЕНИ
# ----------------------------------------------------------------------
def interpolate_telemetry(tele: pd.DataFrame,
                          target_index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Приводит телеметрию к целевому индексу времени.

    Для каждого момента времени target_index:
      - если в tele есть точка с ровно таким же timestamp —
        берётся её значение;
      - иначе значение линейно интерполируется между двумя
        ближайшими по времени точками телеметрии
        (по умолчанию pandas.interpolate(method="time") делает
        именно линейную интерполяцию по времени).

    Никакие строки не выбрасываются — если целевая точка вне
    диапазона tele, значения будут NaN (это ожидаемо).
    """
    t = tele.set_index("timestamp").sort_index()
    # приводим индекс к тому же типу
    target_index = pd.DatetimeIndex(target_index).sort_values()

    # reindex по объединённому индексу, потом интерполируем по времени
    combined = t.reindex(t.index.union(target_index))
    combined = combined.interpolate(method="time", limit_direction="both")

    # выбираем только целевые моменты
    out = combined.reindex(target_index)
    out.index.name = "timestamp"
    return out.reset_index()


# ----------------------------------------------------------------------
# 4. СОПОСТАВЛЕНИЕ ЛАБОРАТОРИИ С ТЕЛЕМЕТРИЕЙ
# ----------------------------------------------------------------------
def match_lab_to_telemetry(lab: pd.DataFrame,
                           tele: pd.DataFrame,
                           window_hours: float = LAB_MATCH_WINDOW_HOURS
                           ) -> pd.DataFrame:
    """
    Для каждой метки времени телеметрии ищет лабораторные пробы,
    попавшие в окно ±window_hours. Если найдены — усредняет
    LIMS-значения по окну. Если нет — все LIMS-колонки = NaN.
    Возвращает DataFrame с колонкой timestamp и всеми LIMS-колонками.
    """
    lab_cols = [c for c in lab.columns if c.startswith("LIMS.")]
    half = pd.Timedelta(hours=window_hours)

    # заранее сортируем и кладём время в индекс для быстрого поиска
    lab_sorted = lab.sort_values("timestamp").reset_index(drop=True)
    lab_times = lab_sorted["timestamp"].values

    rows = []
    for ts in tele["timestamp"]:
        lo = ts - half
        hi = ts + half
        mask = (lab_sorted["timestamp"] >= lo) & (lab_sorted["timestamp"] <= hi)
        sub = lab_sorted.loc[mask, lab_cols]
        if sub.empty:
            row = {c: np.nan for c in lab_cols}
        else:
            row = sub.mean(numeric_only=True).to_dict()
        row["timestamp"] = ts
        rows.append(row)

    matched = pd.DataFrame(rows)[["timestamp"] + lab_cols]
    return matched


# ----------------------------------------------------------------------
# 5. СБОРКА ДВУХ ДАТАСЕТОВ
# ----------------------------------------------------------------------
def build_full_dataset(tele: pd.DataFrame,
                       lab: pd.DataFrame) -> pd.DataFrame:
    """
    Датасет 1: телелеметрия интерполирована, LIMS присоединены
    там, где они есть в окне ±1ч. Строки не выбрасываются.
    """
    tele_interp = interpolate_telemetry(tele, tele["timestamp"])
    lab_matched = match_lab_to_telemetry(lab, tele_interp)
    out = pd.merge(tele_interp, lab_matched, on="timestamp", how="left")
    return out.sort_values("timestamp").reset_index(drop=True)


def build_lab_dataset(full: pd.DataFrame,
                      lab_hint: str = "Mass.Sulfur") -> pd.DataFrame:
    """
    Датасет 2: то же, но оставляем только строки, где
    есть хотя бы один лабораторный замер серы (по hint).
    """
    sulfur_cols = [c for c in full.columns
                   if c.startswith("LIMS.") and lab_hint in c]
    if not sulfur_cols:
        raise KeyError(
            f"Не нашёл ни одной LIMS-колонки с '{lab_hint}'. "
            f"Доступные LIMS: "
            f"{[c for c in full.columns if c.startswith('LIMS.')]}"
        )

    has_lab = full[sulfur_cols].notna().any(axis=1)
    out = full.loc[has_lab].reset_index(drop=True)
    return out


# ----------------------------------------------------------------------
# 6. MAIN
# ----------------------------------------------------------------------
def main():
    print("-> Чтение телеметрии...")
    tele = load_telemetry(TELEMETRY_FILE)
    print(f"   строк: {len(tele)}, колонок: {tele.shape[1]}")
    print(f"   период: {tele['timestamp'].min()} - {tele['timestamp'].max()}")

    print("-> Чтение лаборатории из Excel...")
    lab = load_lab(LAB_FILE, sheet=LAB_SHEET)
    print(f"   проб: {len(lab)}, LIMS-параметров: {lab.shape[1] - 1}")
    print(f"   период: {lab['timestamp'].min()} - {lab['timestamp'].max()}")

    print("-> Формирование полного датасета (телеметрия + интерполяция)...")
    full = build_full_dataset(tele, lab)
    full.to_csv(OUT_FULL, index=False, encoding="utf-8-sig")
    print(f"   сохранено: {OUT_FULL} ({full.shape})")

    print("-> Формирование датасета с лабораторными замерами...")
    lab_ds = build_lab_dataset(full, lab_hint="Mass.Sulfur")
    lab_ds.to_csv(OUT_LAB, index=False, encoding="utf-8-sig")
    print(f"   сохранено: {OUT_LAB} ({lab_ds.shape})")

    sulfur_cols = [c for c in full.columns
                   if c.startswith("LIMS.") and "Sulfur" in c]
    print(f"   колонки с серой: {sulfur_cols}")
    for c in sulfur_cols:
        print(f"     {c}: notna = {full[c].notna().sum()}")


if __name__ == "__main__":
    main()