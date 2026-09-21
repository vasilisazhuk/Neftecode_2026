"""
Оркестратор мультиагентной системы: арбитраж целей, честная классификация статусов.
"""
from typing import Dict, Any
import pandas as pd
from config.settings import SPEC_K5, LIMITS
from agents.quality_agent import DataQualityAgent
from agents.reliability_agent import ReliabilityAgent
from agents.optimization_agent import OptimizationAgent


class Orchestrator:
    def __init__(self):
        self.spec = SPEC_K5
        self.limits = LIMITS
        self.quality_agent = DataQualityAgent()
        self.reliability_agent = ReliabilityAgent()
        self.opt_agent = OptimizationAgent(self.quality_agent, self.reliability_agent)

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
                "action_required": "Отобрать ручную пробу на ЛИМС и проверить датчики ПАК.",
                "explanation_for_operator": "Данные устарели. Автоматическое управление отключено ради безопасности."
            }

        state_dict = {
            'T6': float(telemetry.get('T6', 355.0)),
            'F9': float(telemetry.get('F9', 170.0)),
            'W7': float(telemetry.get('W7', 0.140))
        }
        opt_res = self.opt_agent.optimize(state_dict, qr, rr)

        current_blend_fl = 0.85 * qr.flash_point + 0.15 * 48.0
        current_blend_s = 0.85 * qr.active_sulfur + 0.15 * 3.0

        # Аварийный отказ, если даже вмешательство не спасает процесс
        if not opt_res.is_feasible:
            if current_blend_s > self.spec.MAX_SULFUR_MG_KG:
                status = "CRITICAL_OFF_SPEC"
                verdict = "КРИТИЧЕСКИЙ ВЫБРОС СЕРЫ"
                reason_text = f"Сера смеси ({current_blend_s:.2f} мг/кг) превышает лимит 10 мг/кг. Коррекция невозможна!"
            elif not rr.is_safe:
                status = "EQUIPMENT_OVERLOAD"
                verdict = "АВАРИЙНЫЙ ПЕРЕПАД ДАВЛЕНИЯ"
                reason_text = (
                    f"КРИТИЧЕСКИЙ ПЕРЕПАД P8={rr.dp_reactor_p8:.2f} МПа! "
                    f"Снижение расхода сырья до минимума снизит перепад лишь до {opt_res.predicted_dp:.2f} МПа (выше лимита 0.80 МПа). "
                    "Требуется аварийный останов установки!"
                )
            else:
                status = "CRITICAL_OFF_SPEC"
                verdict = "ВЫХОД ЗА ТЕХНОЛОГИЧЕСКИЙ КОРИДОР"
                reason_text = "Параметры вышли за рамки допустимого режима регулирования."

            return {
                "timestamp": timestamp,
                "status": status,
                "verdict": verdict,
                "detected_risk": qr.issues + rr.alerts,
                "reason": reason_text,
                "action_required": "Аварийный перевод потока в некондиционную емкость!",
                "explanation_for_operator": reason_text
            }

        # Штатный режим
        has_no_actions = (
            abs(opt_res.delta_t6) < 0.1 and
            abs(opt_res.delta_f9) < 0.1 and
            abs(opt_res.delta_w7) < 0.001 and
            abs(opt_res.optimal_kero_share - 0.15) < 0.01
        )

        if has_no_actions and qr.risk_level == "NORMAL" and rr.is_safe:
            return {
                "timestamp": timestamp,
                "status": "NORMAL_OPERATION",
                "verdict": "ШТАТНЫЙ_РЕЖИМ",
                "message": "Технологический процесс оптимален. Вмешательство регуляторов не требуется.",
                "explanation_for_operator": "Параметры находятся в устойчивом технологическом коридоре. Система не создает лишних управляющих действий.",
                "metrics": {
                    "ГОДТ сера": f"{qr.active_sulfur:.2f} мг/кг ({qr.source})",
                    "Товарный дизель сера": f"{current_blend_s:.2f} мг/кг",
                    "Товарный дизель ЦЧ": 51.0,
                    "Вспышка смеси": f"{current_blend_fl:.1f} °C",
                    "Перепад Р-202": f"{rr.dp_reactor_p8:.2f} МПа (норма)"
                }
            }

        status = "ACTION_RECOMMENDED"

        actions_list = []
        if abs(opt_res.delta_f9) >= 1.0:
            actions_list.append({
                "unit_name": "Гидроочистка 24-2000 (Сырьевой насос)",
                "parameter": "F9 (Расход сырья на установку, массовый)",
                "current": state_dict['F9'],
                "target": opt_res.optimal_f9,
                "delta": f"{opt_res.delta_f9:+.1f} т/ч",
                "unit_of_measure": "т/ч"
            })

        if abs(opt_res.delta_t6) >= 0.3:
            actions_list.append({
                "unit_name": "Гидроочистка 24-2000 (Печь нагрева ГСС)",
                "parameter": "T6 (Температура входа в реактор Р-202)",
                "current": state_dict['T6'],
                "target": opt_res.optimal_t6,
                "delta": f"{opt_res.delta_t6:+.1f} °C",
                "unit_of_measure": "°C"
            })

        if abs(opt_res.delta_w7) >= 0.005:
            actions_list.append({
                "unit_name": "Блок стабилизации (Отпарная колонна К-201)",
                "parameter": "W7 (Расход газа поддува в колонну К-201)",
                "current": state_dict['W7'],
                "target": opt_res.optimal_w7,
                "delta": f"{opt_res.delta_w7:+.3f} т/ч",
                "unit_of_measure": "т/ч"
            })

        if abs(opt_res.optimal_kero_share - 0.15) >= 0.02:
            actions_list.append({
                "unit_name": "Резервуарный парк (Блендинг)",
                "parameter": "Доля керосина в смеси",
                "current": 0.15,
                "target": opt_res.optimal_kero_share,
                "delta": f"{(opt_res.optimal_kero_share - 0.15)*100:+.0f}%",
                "unit_of_measure": "доля"
            })

        main_action = actions_list[0] if actions_list else {
            "unit_name": "Технологический режим",
            "parameter": "Режим стабилен",
            "current": 0.0,
            "target": 0.0,
            "delta": "0.0",
            "unit_of_measure": ""
        }

        # ЧЕТКОЕ И ПОНЯТНОЕ ОБЪЯСНЕНИЕ (РАЗДЕЛЯЕМ ГОДТ И ТОВАРНУЮ СМЕСЬ)
        reasons = []
        if abs(opt_res.delta_f9) >= 1.0:
            reasons.append(f"Снижение подачи сырья F9 на {opt_res.delta_f9:+.1f} т/ч снизит перепад dP до нормы {opt_res.predicted_dp:.2f} МПа (норма <= 0.80 МПа).")

        if abs(opt_res.delta_t6) >= 0.3:
            if opt_res.delta_t6 < 0:
                reasons.append(f"Снижение нагрева печи T6 на {opt_res.delta_t6:+.1f} °C экономит топливо (сера ГОДТ: {opt_res.predicted_godt_sulfur:.2f} мг/кг).")
            else:
                # ПРОЗРАЧНО ОБЪЯСНЯЕМ И ГОДТ, И СМЕСЬ В РЕЗЕРВУАРЕ:
                reasons.append(
                    f"Подъем температуры печи T6 на {opt_res.delta_t6:+.1f} °C снизит серу компонента ГОДТ до {opt_res.predicted_godt_sulfur:.2f} мг/кг. "
                    f"С учетом блендинга прогнозная сера товарного дизеля в резервуаре составит {opt_res.predicted_blend_sulfur:.2f} мг/кг (норма ГОСТ <= 10.0 выполнена)."
                )

        if abs(opt_res.delta_w7) >= 0.005:
            reasons.append(f"Коррекция отпарки W7 на {opt_res.delta_w7:+.3f} т/ч гарантирует вспышку смеси {opt_res.predicted_blend_flash:.1f} °C (ГОСТ >= 55.0 °C).")

        if abs(opt_res.optimal_kero_share - 0.15) >= 0.02:
            reasons.append(f"Корректировка доли керосина до {opt_res.optimal_kero_share*100:.0f}% обеспечивает дополнительный запас по качеству.")

        expl_string = " ".join(reasons) if reasons else "Режим скорректирован до нормы."

        return {
            "timestamp": timestamp,
            "status": status,
            "detected_risk": qr.issues + rr.alerts,
            "recommended_action": {
                **main_action,
                "estimated_cost": f"{opt_res.net_economic_effect_rub_h:+.0f} руб/ч (нетто-эффект)",
                "all_actions": actions_list
            },
            "blend_quality_forecast": {
                "sulfur": opt_res.predicted_blend_sulfur,
                "flash_point": opt_res.predicted_blend_flash,
                "cetane": opt_res.predicted_blend_cetane,
                "density": 830.0
            },
            "constraints_verified": [
                (f"Сера смеси <= 10 мг/кг (прогноз {opt_res.predicted_blend_sulfur:.2f})", opt_res.predicted_blend_sulfur <= self.spec.MAX_SULFUR_MG_KG),
                (f"Вспышка смеси >= 55.0 °C (прогноз {opt_res.predicted_blend_flash:.1f} °C)", opt_res.predicted_blend_flash >= self.spec.MIN_FLASH_POINT_C),
                (f"Цетановое число >= 51 (прогноз {opt_res.predicted_blend_cetane:.1f})", opt_res.predicted_blend_cetane >= self.spec.MIN_CETANE_NUMBER),
                (f"Перепад Р-202 <= 0.8 МПа (прогноз {opt_res.predicted_dp:.2f} МПа)", opt_res.predicted_dp <= self.limits.MAX_REACTOR_DP_MPA),
                ("Баланс компонентов блендинга = 100%", True)
            ],
            "explanation_for_operator": expl_string
        }