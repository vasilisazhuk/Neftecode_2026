"""
Базовые контракты и структуры данных мультиагентной системы (МАС).
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class QualityReport:
    active_sulfur: float
    source: str                 # 'LIMS', 'PAK'
    source_age_hours: float
    is_stale: bool
    risk_level: str             # 'NORMAL', 'WARNING', 'OFF_SPEC', 'CRITICAL'
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
class OptimizationResult:
    is_feasible: bool            # Удалось ли найти безопасное допустимое решение
    optimal_t6: float            # Рекомендуемая температура входа Р-202 (°C)
    optimal_f9: float            # Рекомендуемый расход сырья (т/ч)
    optimal_w7: float            # Рекомендуемый расход газа отпарки К-201 (т/ч)
    optimal_kero_share: float    # Рекомендуемая доля керосина в блендинге (0..1)
    optimal_additive_kg_t: float # Рекомендуемый ввод цетаноповышающей присадки (кг/т)
    predicted_godt_sulfur: float # Прогноз серы ГОДТ (мг/кг)
    predicted_blend_sulfur: float# Прогноз серы смеси (мг/кг)
    predicted_blend_flash: float # Прогноз вспышки смеси (°C)
    predicted_blend_cetane: float# Прогноз цетанового числа смеси
    predicted_dp: float          # Прогноз перепада давления Р-202 (МПа)
    delta_t6: float
    delta_f9: float
    delta_w7: float
    net_economic_effect_rub_h: float  # Экономический эффект (руб/ч)
    solver_message: str


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
    issue_type: str = "GENERAL"