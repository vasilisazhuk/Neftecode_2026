"""Модуль очистки и парсинга сырых данных телеметрии и лаборатории."""

import numpy as np
import pandas as pd

RU_MONTHS = {
    'янв': '01',
    'фев': '02',
    'мар': '03',
    'апр': '04',
    'май': '05',
    'июн': '06',
    'июл': '07',
    'авг': '08',
    'сен': '09',
    'окт': '10',
    'ноя': '11',
    'дек': '12',
}


def parse_russian_dates(series: pd.Series) -> pd.Series:
  """Парсинг смешанных форматов дат с русскими названиями месяцев."""
  parsed = pd.to_datetime(series, errors='coerce')
  mask = parsed.isna() & series.notna()

  if mask.any():
    text_dates = series[mask].astype(str).str.lower().str.strip()
    for ru, num in RU_MONTHS.items():
      text_dates = text_dates.str.replace(ru, num, regex=False)
    parsed_rescued = pd.to_datetime(text_dates, errors='coerce', dayfirst=True)
    parsed.loc[mask] = parsed_rescued

  return parsed


def clean_numeric(series: pd.Series) -> pd.Series:
  """Приведение значений к числам с удалением текстового мусора ('Pt Created')."""
  s = (
      series.astype(str)
      .str.replace(',', '.', regex=False)
      .str.replace(' ', '', regex=False)
  )
  return pd.to_numeric(s, errors='coerce')