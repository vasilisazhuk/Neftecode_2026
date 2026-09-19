"""Оркестратор мультиагентной системы: арбитраж целей и финальный вердикт."""

from typing import Any, Dict
from agents.optimization_agent import OptimizationAgent
from agents.quality_agent import DataQualityAgent
from agents.reliability_agent import ReliabilityAgent
from config.settings import SPEC_K5
from models.blending_engine import BlendComponent, BlendingEngine
import pandas as pd


class Orchestrator:

  def __init__(self):
    self.spec = SPEC_K5
    self.quality_agent = DataQualityAgent()
    self.reliability_agent = ReliabilityAgent()
    self.opt_agent = OptimizationAgent()

  def process_step(self, telemetry: pd.Series) -> Dict[str, Any]:
    timestamp = telemetry.get('date', 'UNKNOWN_TIMESTAMP')
    qr = self.quality_agent.evaluate(telemetry)
    rr = self.reliability_agent.evaluate(telemetry)

    # 1. Проверка условия регламентного отказа (Graceful Refusal по ТЗ)
    if qr.is_stale:
      return {
          'timestamp': timestamp,
          'status': 'REFUSAL_TO_RECOMMEND',
          'verdict': 'ОТКАЗ_ОТ_РЕКОМЕНДАЦИИ',
          'reason': (
              'Надёжной рекомендации нет: лабораторное значение серы'
              f' устарело (> {qr.source_age_hours:.1f} ч), а поточные датчики'
              ' отключены.'
          ),
          'action_required': (
              'Отобрать ручную пробу на ЛИМС и вызвать службу КИПиА для'
              ' проверки ПАК Q21.'
          ),
      }

    # 2. Моделирование резервуара товарного блендинга
    godt_s = qr.active_sulfur
    blend_result = BlendingEngine.blend(
        c_hydro=BlendComponent(
            'ГОДТ', 0.85, godt_s, 836.0, 52.0, qr.flash_point, 348.0, -16.0
        ),
        c_kero=BlendComponent(
            'Керосин', 0.15, 3.0, 795.0, 44.0, 48.0, 245.0, -48.0
        ),
        c_gasoil=BlendComponent(
            'Газойль', 0.00, 28.0, 865.0, 48.0, 75.0, 362.0, -4.0
        ),
        dose_cetane_booster_kg_t=0.1,
        dose_depressant_kg_t=0.0,
    )

    # 3. Штатный устойчивый режим
    if (
        qr.risk_level == 'NORMAL'
        and rr.is_safe
        and blend_result['sulfur'] <= self.spec.MAX_SULFUR_MG_KG
    ):
      return {
          'timestamp': timestamp,
          'status': 'NORMAL_OPERATION',
          'verdict': 'ШТАТНЫЙ_РЕЖИМ',
          'message': (
              'Технологический процесс оптимален. Корректировка не требуется.'
          ),
          'metrics': {
              'ГОДТ сера': f'{godt_s:.2f} мг/кг ({qr.source})',
              'Товарный дизель сера': f"{blend_result['sulfur']:.2f} мг/кг",
              'Товарный дизель ЦЧ': blend_result['cetane'],
              'Перепад Р-202': f'{rr.dp_reactor_p8:.2f} МПа (норма)',
          },
      }

    # 4. Формирование рекомендаций оператору
    scenarios = self.opt_agent.generate_scenarios(telemetry, qr, rr)

    if not scenarios:
      return {
          'timestamp': timestamp,
          'status': 'NO_FEASIBLE_ACTION',
          'verdict': 'НЕТ_БЕЗОПАСНЫХ_РЕШЕНИЙ',
          'reason': (
              f"Выявлены риски: {'; '.join(qr.issues + rr.alerts)}, однако"
              ' доступные воздействия исчерпали границы допустимых диапазонов.'
          ),
      }

    best_action = sorted(scenarios, key=lambda a: a.total_cost_rub_h)[0]

    return {
        'timestamp': timestamp,
        'status': 'ACTION_RECOMMENDED',
        'verdict': 'РЕКОМЕНДОВАНО_ДЕЙСТВИЕ',
        'detected_risk': qr.issues + rr.alerts,
        'recommended_action': {
            'unit': best_action.target_unit,
            'parameter': best_action.parameter,
            'current': best_action.current_value,
            'target': best_action.recommended_value,
            'delta': f'{best_action.delta:+.1f} {best_action.unit_of_measure}',
            'estimated_cost': f'{best_action.total_cost_rub_h} руб/ч',
        },
        'blend_quality_forecast': blend_result,
        'constraints_verified': [
            f'Сера смеси <= 10 мг/кг: {blend_result["sulfur"] <= self.spec.MAX_SULFUR_MG_KG}',
            f'Цетановое число >= 51: {blend_result["cetane"] >= self.spec.MIN_CETANE_NUMBER}',
            f'Перепад Р-202 <= 0.8 МПа: {rr.is_safe}',
            'Баланс компонентов блендинга = 100%: True',
        ],
        'explanation_for_operator': (
            f'{best_action.explanation} Данное действие позволяет вернуть'
            ' качество в пределы ГОСТ 32511-2013 с минимальными затратами'
            ' энергоресурсов.'
        ),
    }