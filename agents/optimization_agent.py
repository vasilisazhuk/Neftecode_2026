"""
Агент многопараметрической оптимизации (управление T6, F9, W7 и блендингом).
Поддерживает выработку пакета действий при множественных нарушениях.
"""
from typing import List
import pandas as pd
from config.settings import SPEC_K5, LIMITS, ECONOMICS
from agents.base import QualityReport, ReliabilityReport, ActionCandidate


class OptimizationAgent:
    def __init__(self):
        self.econ = ECONOMICS
        self.limits = LIMITS
        self.spec = SPEC_K5

    def generate_scenarios(
        self,
        state: pd.Series,
        qr: QualityReport,
        rr: ReliabilityReport
    ) -> List[ActionCandidate]:
        candidates = []

        blended_flash_estimate = 0.85 * qr.flash_point + 0.15 * 48.0
        flash_needs_fix = blended_flash_estimate < self.spec.MIN_FLASH_POINT_C

        # 1. ЗАЩИТА ОБОРУДОВАНИЯ (Перепад dP P8 > 0.8 МПа)
        if not rr.is_safe and rr.dp_reactor_p8 > self.limits.MAX_REACTOR_DP_MPA:
            curr_f9 = state.get('F9', 170.0)
            feed_cut = round(curr_f9 * 0.10, 1)
            # Гидравлический расчет: перепад снизится пропорционально квадрату снижения расхода
            predicted_dp = round(rr.dp_reactor_p8 * ((curr_f9 - feed_cut) / curr_f9)**2, 2)

            candidates.append(ActionCandidate(
                target_unit="Гидроочистка 24-2000 (Сырьевой насос)",
                parameter="F9 (Расход сырья на установку, массовый)",
                current_value=curr_f9,
                recommended_value=curr_f9 - feed_cut,
                delta=-feed_cut,
                unit_of_measure="т/ч",
                energy_impact_rub_h=0.0,
                additive_cost_rub_h=0.0,
                total_cost_rub_h=5000.0,
                explanation=(
                    f"АВАРИЙНЫЙ ПЕРЕПАД P8={rr.dp_reactor_p8:.2f} МПа! Снижение подачи сырья на -{feed_cut:.1f} т/ч "
                    f"снизит гидравлическое сопротивление до безопасных ~{predicted_dp:.2f} МПа (норма <= 0.80 МПа)."
                ),
                issue_type="EQUIPMENT_DP"
            ))

        # 2. КОРРЕКЦИЯ ВСПЫШКИ (W7) - выполняется ДАЖЕ если реактор разгружается!
        if flash_needs_fix:
            curr_w7 = state.get('W7', 0.14)
            flash_deficit = self.spec.MIN_FLASH_POINT_C - blended_flash_estimate
            needed_w7_boost = min(max(flash_deficit * 0.008, 0.025), 0.080)
            w7_target = round(curr_w7 + needed_w7_boost, 3)
            delta_w7 = round(w7_target - curr_w7, 3)

            candidates.append(ActionCandidate(
                target_unit="Блок стабилизации (Отпарная колонна К-201)",
                parameter="W7 (Расход газа поддува в колонну К-201)",
                current_value=curr_w7,
                recommended_value=w7_target,
                delta=delta_w7,
                unit_of_measure="т/ч",
                energy_impact_rub_h=round(delta_w7 * 15000, 0),
                additive_cost_rub_h=0.0,
                total_cost_rub_h=round(delta_w7 * 15000, 0),
                explanation=(
                    f"Вспышка смеси ({blended_flash_estimate:.1f} °C) ниже нормы ГОСТ (>= 55 °C). "
                    f"Увеличение отпарки легких бензинов в К-201 на +{delta_w7:.3f} т/ч для подъема IBP."
                ),
                issue_type="FLASH_POINT"
            ))

        # 3. КОРРЕКЦИЯ СЕРЫ (T6 печи Р-202) - если перепад в норме
        if qr.active_sulfur >= 8.5 and rr.dp_reactor_p8 <= self.limits.MAX_REACTOR_DP_MPA:
            current_t6 = rr.inlet_temp_t6
            feed_tph = state.get('F9', 170.0)
            target_s = 7.5
            delta_s = qr.active_sulfur - target_s
            temp_rise = min(max(delta_s / 0.3, 0.5), self.limits.MAX_DELTA_TEMP_CYCLE)

            if rr.bed_temp_t11 + temp_rise <= self.limits.MAX_BED_TEMP_C:
                energy_cost = temp_rise * feed_tph * 0.0006 * self.econ.COST_FUEL_GAS_RUB_GCAL
                candidates.append(ActionCandidate(
                    target_unit="Гидроочистка 24-2000 (Печь нагрева ГСС)",
                    parameter="T6 (Температура входа в реактор Р-202)",
                    current_value=current_t6,
                    recommended_value=current_t6 + temp_rise,
                    delta=round(temp_rise, 1),
                    unit_of_measure="°C",
                    energy_impact_rub_h=round(energy_cost, 0),
                    additive_cost_rub_h=0.0,
                    total_cost_rub_h=round(energy_cost, 0),
                    explanation=f"Подъем температуры нагрева на +{temp_rise:.1f} °C углубит обессеривание.",
                    issue_type="SULFUR"
                ))

        # 4. ПОЛУЧЕНИЕ ПРИБЫЛИ (ДОЗАГРУЗКА СЫРЬЯ)
        if (qr.risk_level == "NORMAL" and qr.active_sulfur < 7.5
            and not flash_needs_fix and rr.dp_reactor_p8 < 0.40):
            curr_f9 = state.get('F9', 170.0)
            feed_boost = round(curr_f9 * 0.04, 1)
            candidates.append(ActionCandidate(
                target_unit="Гидроочистка 24-2000 (Сырьевой насос)",
                parameter="F9 (Расход сырья на установку, массовый)",
                current_value=curr_f9,
                recommended_value=curr_f9 + feed_boost,
                delta=feed_boost,
                unit_of_measure="т/ч",
                energy_impact_rub_h=0.0,
                additive_cost_rub_h=0.0,
                total_cost_rub_h=-25000.0,
                explanation=(
                    f"ЗОЛОТОЕ ТЕХНОЛОГИЧЕСКОЕ ОКНО: сера {qr.active_sulfur:.1f} мг/кг, перепад {rr.dp_reactor_p8:.2f} МПа. "
                    f"Увеличение подачи сырья на +{feed_boost:.1f} т/ч дает прирост выработки товарного ДТ."
                ),
                issue_type="OPTIMIZATION_THROUGHPUT"
            ))

        return candidates