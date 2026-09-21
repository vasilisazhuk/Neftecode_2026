"""
Агент многопараметрической оптимизации технологического режима и блендинга.
"""
from typing import Dict, Any, List, Optional
import math
import pandas as pd
from config.settings import SPEC_K5, LIMITS, ECONOMICS
from agents.base import QualityReport, ReliabilityReport, OptimizationResult
from agents.quality_agent import DataQualityAgent
from agents.reliability_agent import ReliabilityAgent


class OptimizationAgent:
    def __init__(self, quality_agent: DataQualityAgent, reliability_agent: ReliabilityAgent):
        self.spec = SPEC_K5
        self.limits = LIMITS
        self.econ = ECONOMICS
        self.qa = quality_agent
        self.ra = reliability_agent

    def optimize(
        self,
        telemetry: Dict[str, float],
        qr: QualityReport,
        rr: ReliabilityReport
    ) -> OptimizationResult:
        curr_t6 = float(telemetry.get('T6', 355.0))
        curr_f9 = float(telemetry.get('F9', 170.0))
        curr_w7 = float(telemetry.get('W7', 0.140))

        blended_flash_estimate = 0.85 * qr.flash_point + 0.15 * 48.0

        # ЗОНА НЕЧУВСТВИТЕЛЬНОСТИ: В штатном коридоре держим уставки
        is_in_normal_corridor = (
            4.0 <= qr.active_sulfur <= 8.5 and
            blended_flash_estimate >= self.spec.MIN_FLASH_POINT_C and
            rr.dp_reactor_p8 <= 0.75 and
            curr_t6 <= 372.0
        )

        if is_in_normal_corridor:
            return OptimizationResult(
                is_feasible=True,
                optimal_t6=curr_t6,
                optimal_f9=curr_f9,
                optimal_w7=curr_w7,
                optimal_kero_share=0.15,
                optimal_additive_kg_t=0.10,
                predicted_godt_sulfur=round(qr.active_sulfur, 2),
                predicted_blend_sulfur=round(0.85 * qr.active_sulfur + 0.15 * 3.0, 2),
                predicted_blend_flash=round(blended_flash_estimate, 1),
                predicted_blend_cetane=51.0,
                predicted_dp=round(rr.dp_reactor_p8, 2),
                delta_t6=0.0,
                delta_f9=0.0,
                delta_w7=0.0,
                net_economic_effect_rub_h=0.0,
                solver_message="Процесс в нормальном коридоре. Вмешательство не требуется."
            )

        # 1. Точный расчет расхода сырья F9 при перепаде
        if rr.dp_reactor_p8 > self.limits.MAX_REACTOR_DP_MPA:
            needed_ratio = math.sqrt(0.74 / rr.dp_reactor_p8)
            target_f9 = max(round(curr_f9 * needed_ratio, 1), 110.0)
            f9_candidates = [target_f9]
        elif rr.dp_reactor_p8 > 0.75:
            f9_candidates = [round(curr_f9 * 0.95, 1), curr_f9]
        else:
            f9_candidates = [curr_f9]

        # 2. Кандидаты для T6 (Печь Р-202)
        if qr.active_sulfur > 8.5:
            t6_candidates = [curr_t6 + 1.0, curr_t6 + 2.0, curr_t6 + 3.0]
        elif qr.active_sulfur < 4.0 and curr_t6 > 365.0:
            t6_candidates = [curr_t6 - 2.0, curr_t6 - 1.0]
        elif curr_t6 > 375.0:
            t6_candidates = [curr_t6 - 3.0, curr_t6 - 2.0]
        else:
            t6_candidates = [curr_t6]

        max_safe_t6 = max(375.0, min(385.0, self.limits.MAX_BED_TEMP_C - rr.delta_t))
        t6_candidates = [round(t, 1) for t in t6_candidates if 340.0 <= t <= max_safe_t6]
        if not t6_candidates:
            t6_candidates = [curr_t6]

        # 3. Газ отпарки W7
        if blended_flash_estimate < self.spec.MIN_FLASH_POINT_C:
            w7_candidates = [curr_w7 + 0.025, curr_w7 + 0.040]
        else:
            w7_candidates = [curr_w7]

        # Если сера сырья высокая (> 11), берем чуть больше керосина (18%), чтобы не балансировать на 9.97!
        if qr.active_sulfur > 11.0:
            kero_candidates = [0.18, 0.20]
        elif blended_flash_estimate < self.spec.MIN_FLASH_POINT_C:
            kero_candidates = [0.10, 0.15]
        else:
            kero_candidates = [0.15]

        add_candidates = [0.10, 0.20]

        valid_scenarios = []

        for t6 in t6_candidates:
            for f9 in f9_candidates:
                for w7 in w7_candidates:
                    for kero in kero_candidates:
                        for add_dose in add_candidates:
                            pred_s = self.qa.predict_godt_sulfur(qr.active_sulfur, curr_t6, t6, curr_f9, f9)
                            pred_fl = self.qa.predict_godt_flash(qr.flash_point, curr_w7, w7)
                            pred_dp = self.ra.predict_reactor_dp(rr.dp_reactor_p8, curr_f9, f9)

                            blend_s = (1.0 - kero) * pred_s + kero * 3.0
                            blend_fl = (1.0 - kero) * pred_fl + kero * 48.0
                            blend_cn = (1.0 - kero) * 52.0 + kero * 44.0 + (add_dose * 2.5)

                            if blend_s > self.spec.MAX_SULFUR_MG_KG:
                                continue
                            if blend_fl < self.spec.MIN_FLASH_POINT_C:
                                continue
                            if pred_dp > self.limits.MAX_REACTOR_DP_MPA:
                                continue
                            if blend_cn < self.spec.MIN_CETANE_NUMBER:
                                continue

                            fuel_cost_diff = (t6 - curr_t6) * f9 * 0.0006 * self.econ.COST_FUEL_GAS_RUB_GCAL
                            gas_cost_diff = (w7 - curr_w7) * 15000.0
                            add_cost = (add_dose / 1000.0) * f9 * self.econ.COST_ADDITIVE_RUB_TON
                            throughput_gain = (f9 - curr_f9) * 15000.0

                            net_benefit = throughput_gain - (fuel_cost_diff + gas_cost_diff + add_cost)

                            valid_scenarios.append({
                                't6': t6,
                                'f9': f9,
                                'w7': w7,
                                'kero': kero,
                                'add': add_dose,
                                'blend_s': blend_s,
                                'blend_fl': blend_fl,
                                'blend_cn': blend_cn,
                                'pred_dp': pred_dp,
                                'pred_godt_s': pred_s,
                                'net_benefit': net_benefit
                            })

        if not valid_scenarios:
            max_cut_f9 = 110.0
            pred_dp_min = self.ra.predict_reactor_dp(rr.dp_reactor_p8, curr_f9, max_cut_f9)
            return OptimizationResult(
                is_feasible=False,
                optimal_t6=curr_t6,
                optimal_f9=max_cut_f9,
                optimal_w7=curr_w7,
                optimal_kero_share=0.15,
                optimal_additive_kg_t=0.0,
                predicted_godt_sulfur=qr.active_sulfur,
                predicted_blend_sulfur=0.85 * qr.active_sulfur + 0.15 * 3.0,
                predicted_blend_flash=0.85 * qr.flash_point + 0.15 * 48.0,
                predicted_blend_cetane=50.8,
                predicted_dp=round(pred_dp_min, 2),
                delta_t6=0.0,
                delta_f9=round(max_cut_f9 - curr_f9, 1),
                delta_w7=0.0,
                net_economic_effect_rub_h=-25000.0,
                solver_message="Превышены пределы технологического регулирования"
            )

        best = sorted(valid_scenarios, key=lambda s: s['net_benefit'], reverse=True)[0]

        return OptimizationResult(
            is_feasible=True,
            optimal_t6=round(best['t6'], 1),
            optimal_f9=round(best['f9'], 1),
            optimal_w7=round(best['w7'], 3),
            optimal_kero_share=round(best['kero'], 2),
            optimal_additive_kg_t=round(best['add'], 2),
            predicted_godt_sulfur=round(best['pred_godt_s'], 2),
            predicted_blend_sulfur=round(best['blend_s'], 2),
            predicted_blend_flash=round(best['blend_fl'], 1),
            predicted_blend_cetane=round(best['blend_cn'], 1),
            predicted_dp=round(best['pred_dp'], 2),
            delta_t6=round(best['t6'] - curr_t6, 1),
            delta_f9=round(best['f9'] - curr_f9, 1),
            delta_w7=round(best['w7'] - curr_w7, 3),
            net_economic_effect_rub_h=round(best['net_benefit'], 0),
            solver_message=f"Найдено {len(valid_scenarios)} допустимых вариантов. Выбран оптимум."
        )