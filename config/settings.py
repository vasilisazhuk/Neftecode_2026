"""Параметры и константы производственной системы."""

from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RESOURCES_DIR = BASE_DIR / 'resources'


@dataclass(frozen=True)
class SpecGOSTK5:
  """Нормы ГОСТ 32511-2013 для дизельного топлива Евро-5 (Класс К5)."""

  MAX_SULFUR_MG_KG: float = 10.0  # Сера не более 10.0 мг/кг (жесткое ограничение)
  MIN_CETANE_NUMBER: float = 51.0  # Цетановое число не менее 51.0
  MIN_DENSITY_15C: float = 820.0  # Плотность при 15°C не менее 820 кг/м3
  MAX_DENSITY_15C: float = 845.0  # Плотность при 15°C не более 845 кг/м3
  MIN_FLASH_POINT_C: float = (
      55.0  # Температура вспышки в закрытом тигле не ниже 55 °C
  )
  MAX_T95_C: float = 360.0  # Температура выкипания 95% не выше 360 °C
  MAX_CFPP_SUMMER_C: float = -5.0  # Предельная температура фильтруемости (сорт C)


@dataclass(frozen=True)
class EquipmentLimits:
  """Технологические ограничения оборудования установки 24-2000."""

  MAX_REACTOR_DP_MPA: float = 0.80  # Предельный перепад P8 на реакторе Р-202 (МПа)
  MAX_BED_TEMP_C: float = 385.0  # Максимальная температура катализатора T11 (°C)
  MAX_DELTA_TEMP_CYCLE: float = (
      3.0  # Максимальный шаг коррекции нагрева за 1 цикл
  )
  LIMS_MAX_FRESHNESS_HOURS: float = (
      18.0  # Порог актуальности лабораторного анализа
  )
  LAB_REPORTING_DELAY_HOURS: float = (
      4.0  # Физический лаг доставки и выполнения пробы
  )


@dataclass(frozen=True)
class EconomicsConfig:
  """Экономическая модель по разъяснениям экспертов."""

  COST_DIESEL_BASE_RUB_TON: float = 60_000.0  # Базовая стоимость 1 т ДТ
  COST_ADDITIVE_RUB_TON: float = (
      60_000.0 * 100.0
  )  # Присадка в 100 раз дороже ДТ!
  COST_FUEL_GAS_RUB_GCAL: float = 2_500.0  # Стоимость топливного газа печи
  MAX_ADDITIVE_PERCENT: float = (
      3.0  # Максимальный ввод цетаноповышающей присадки
  )


SPEC_K5 = SpecGOSTK5()
LIMITS = EquipmentLimits()
ECONOMICS = EconomicsConfig()