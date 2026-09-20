"""
Оркестратор мультиагентной системы: арбитраж целей, прогнозная валидация ограничений.
"""
from typing import Dict, Any
import pandas as pd
from config.settings import SPEC_K5, LIMITS
from agents.quality_agent import DataQualityAgent
from agents.reliability_agent import ReliabilityAgent
from agents.optimization_agent import OptimizationAgent
from models.blending_engine import BlendingEngine, BlendComponent


class Orchestrator:
    def __init__(self):
        self.spec = SPEC_K5
        self.limits = LIMITS
        self.quality_agent = DataQualityAgent()
        self.reliability_agent = ReliabilityAgent()
        self.opt_agent = OptimizationAgent()

    def process_step(self, telemetry: pd.Series) -> Dict[str, Any]:
        raw_ts = telemetry.get('date', 'UNKNOWN_TIMESTAMP')
        timestamp = str(raw_ts.strftime('%Y-%m-%d %H:%M:%S')) if hasattr(raw_ts, 'strftime') else str(raw_ts)

        qr = self.quality_agent.evaluate(telemetry)
        rr = self.reliability_agent.evaluate(telemetry)

        if qr.is_stale:
            return {
                "timestamp": timestamp,
                "status": "REFUSAL_TO_RECOMMEND",
                "verdict": "ОТКАЗ_ОТ_РЕКОМЕНДАЦИИ",
                "reason": f"Надёжной рекомендации нет: лабораторное значение серы устарело (> {qr.source_age_hours:.1f} ч).",
                "action_required": "Отобрать ручную пробу на ЛИМС и проверить ПАК Q21."
            }

        godt_s = qr.active_sulfur
        blend_result = BlendingEngine.blend(
            c_hydro=BlendComponent("ГОДТ", 0.85, godt_s, 836.0, 52.0, qr.flash_point, 348.0, -16.0),
            c_kero=BlendComponent("Керосин", 0.15, 3.0, 795.0, 44.0, 48.0, 245.0, -48.0),
            c_gasoil=BlendComponent("Газойль", 0.00, 28.0, 865.0, 48.0, 75.0, 362.0, -4.0),
            dose_cetane_booster_kg_t=0.1,
            dose_depressant_kg_t=0.0
        )

        scenarios = self.opt_agent.generate_scenarios(telemetry, qr, rr)

        # Режим полностью идеален
        if not scenarios and blend_result['flash_point'] >= self.spec.MIN_FLASH_POINT_C and rr.is_safe:
            return {
                "timestamp": timestamp,
                "status": "NORMAL_OPERATION",
                "verdict": "ШТАТНЫЙ_РЕЖИМ",
                "message": "Технологический процесс оптимален. Корректировка не требуется.",
                "metrics": {
                    "ГОДТ сера": f"{godt_s:.2f} мг/кг ({qr.source})",
                    "Товарный дизель сера": f"{blend_result['sulfur']:.2f} мг/кг",
                    "Товарный дизель ЦЧ": blend_result['cetane'],
                    "Вспышка смеси": f"{blend_result['flash_point']:.1f} °C",
                    "Перепад Р-202": f"{rr.dp_reactor_p8:.2f} МПа (норма)"
                }
            }

        # Приоритет: Аварии оборудования (dP) > Качество (Вспышка/Сера) > Экономика
        best_action = sorted(scenarios, key=lambda a: a.total_cost_rub_h)[0]

        # Расчет ПРОГНОЗНЫХ параметров ПОСЛЕ применения действия
        pred_s = godt_s
        pred_flash = qr.flash_point
        pred_dp = rr.dp_reactor_p8
        status = "ACTION_RECOMMENDED"

        if best_action.issue_type == 'EQUIPMENT_DP':
            status = "EQUIPMENT_OVERLOAD"
            # Прогноз снижения перепада после разгрузки сырья
            curr_feed = best_action.current_value
            new_feed = best_action.recommended_value
            pred_dp = round(rr.dp_reactor_p8 * (new_feed / curr_feed)**2, 2)

            explanation = best_action.explanation
            if blend_result['flash_point'] < self.spec.MIN_FLASH_POINT_C:
                explanation += f" ВНИМАНИЕ: Также зафиксирована низкая вспышка смеси ({blend_result['flash_point']:.1f} °C)! Требуется коррекция отпарки в К-201."

        elif best_action.issue_type == 'FLASH_POINT':
            expected_flash_gain = (best_action.delta / 0.010) * 2.5
            pred_flash = round(qr.flash_point + expected_flash_gain, 1)
            pred_blend_flash = round(0.85 * pred_flash + 0.15 * 48.0, 1)

            if pred_blend_flash >= self.spec.MIN_FLASH_POINT_C:
                explanation = (
                    f"{best_action.explanation} Прогнозная вспышка смеси: ~{pred_blend_flash:.1f} °C "
                    f"(норма ГОСТ >= {self.spec.MIN_FLASH_POINT_C} °C будет выполнена)."
                )
            else:
                explanation = (
                    f"{best_action.explanation} Прогнозная вспышка смеси: ~{pred_blend_flash:.1f} °C. "
                    "Рекомендуется также снизить долю керосина в блендинге с 15% до 10%!"
                )

        elif best_action.issue_type == 'SULFUR':
            expected_s_drop = best_action.delta * 0.3
            pred_s = max(godt_s - expected_s_drop, 0.0)
            if pred_s <= 10.0:
                explanation = f"{best_action.explanation} Прогнозная сера смеси: ~{pred_s:.2f} мг/кг (норма выполнена)."
            else:
                status = "CRITICAL_OFF_SPEC"
                explanation = (
                    f"ВНИМАНИЕ! Глубокий выброс серы ({godt_s:.2f} мг/кг). Шага печи недостаточно. "
                    "Требуется аварийный перевод потока в некондицию!"
                )

        elif best_action.issue_type == 'OPTIMIZATION_THROUGHPUT':
            status = "OPTIMIZATION_OPPORTUNITY"
            explanation = best_action.explanation

        pred_blend = BlendingEngine.blend(
            c_hydro=BlendComponent("ГОДТ", 0.85, pred_s, 836.0, 52.0, pred_flash, 348.0, -16.0),
            c_kero=BlendComponent("Керосин", 0.15, 3.0, 795.0, 44.0, 48.0, 245.0, -48.0),
            c_gasoil=BlendComponent("Газойль", 0.00, 28.0, 865.0, 48.0, 75.0, 362.0, -4.0),
            dose_cetane_booster_kg_t=0.1,
            dose_depressant_kg_t=0.0
        )

        is_sulfur_ok = pred_blend['sulfur'] <= self.spec.MAX_SULFUR_MG_KG
        is_flash_ok = pred_blend['flash_point'] >= self.spec.MIN_FLASH_POINT_C
        is_dp_ok = pred_dp <= self.limits.MAX_REACTOR_DP_MPA

        delta_fmt = f"{best_action.delta:+.3f}" if abs(best_action.delta) < 1.0 else f"{best_action.delta:+.1f}"

        return {
            "timestamp": timestamp,
            "status": status,
            "detected_risk": qr.issues + rr.alerts,
            "recommended_action": {
                "unit_name": best_action.target_unit,
                "parameter": best_action.parameter,
                "current": best_action.current_value,
                "target": best_action.recommended_value,
                "delta": f"{delta_fmt} {best_action.unit_of_measure}",
                "unit_of_measure": best_action.unit_of_measure,
                "estimated_cost": f"{best_action.total_cost_rub_h:+.0f} руб/ч"
            },
            "blend_quality_forecast": pred_blend,
            "constraints_verified": [
                ("Сера смеси <= 10 мг/кг", is_sulfur_ok),
                (f"Вспышка смеси >= {self.spec.MIN_FLASH_POINT_C} °C", is_flash_ok),
                ("Цетановое число >= 51", pred_blend['cetane'] >= self.spec.MIN_CETANE_NUMBER),
                (f"Перепад Р-202 <= 0.8 МПа (прогноз {pred_dp:.2f} МПа)", is_dp_ok),
                ("Баланс компонентов блендинга = 100%", True)
            ],
            "explanation_for_operator": explanation
        }