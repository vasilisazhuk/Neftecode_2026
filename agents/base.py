"""Контракты обмена данными между агентами МАС."""

from dataclasses import dataclass
from typing import List


@dataclass
class QualityReport:
  active_sulfur: float
  source: str
  source_age_hours: float
  is_stale: bool
  risk_level: str  # 'NORMAL', 'WARNING', 'OFF_SPEC', 'CRITICAL'
  flash_point: float
  issues: List[str]


@dataclass
class ReliabilityReport:
  is_safe: bool
  dp_reactor_p8: float
  bed_temp_t11: float
  inlet_temp_t6: float
  delta_t: float
  alerts: List[str]


@dataclass
class ActionCandidate:
  target_unit: str
  parameter: str
  current_value: float
  recommended_value: float
  delta: float
  unit_of_measure: str
  energy_impact_rub_h: float
  additive_cost_rub_h: float
  total_cost_rub_h: float
  explanation: str
  issue_type: str  # 'EQUIPMENT_DP', 'FLASH_POINT', 'SULFUR', 'OPTIMIZATION_THROUGHPUT'