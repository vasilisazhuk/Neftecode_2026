"""Агент генерации и оценки экономической эффективности управляющих воздействий."""

from typing import List
from agents.base import ActionCandidate, QualityReport, ReliabilityReport
from config.settings import ECONOMICS, LIMITS, SPEC_K5
import pandas as pd


class OptimizationAgent:

  def __init__(self):
    self.econ = ECONOMICS
    self.limits = LIMITS
    self.spec = SPEC_K5

  def generate_scenarios(
      self,
      state: pd.Series,
      qr: QualityReport,
      rr: ReliabilityReport,
  ) -> List[ActionCandidate]:
    candidates = []

    # При стабильном режиме не дергаем регуляторы (требование ТЗ)
    if qr.risk_level == 'NORMAL' and rr.is_safe:
      return candidates

    current_t6 = rr.inlet_temp_t6
    feed_tph = state.get('F9', 170.0)

    # Сценарий 1: Коррекция серы через температуру входа печи Р-202 (тег T6)
    if qr.risk_level in ['WARNING', 'OFF_SPEC']:
      target_s = 7.5
      delta_s = qr.active_sulfur - target_s
      temp_rise = min(max(delta_s / 0.3, 0.5), self.limits.MAX_DELTA_TEMP_CYCLE)

      if rr.bed_temp_t11 + temp_rise <= self.limits.MAX_BED_TEMP_C:
        energy_cost = (
            temp_rise * feed_tph * 0.0006 * self.econ.COST_FUEL_GAS_RUB_GCAL
        )

        candidates.append(
            ActionCandidate(
                target_unit='Гидроочистка 24-2000 (Печь нагрева ГСС)',
                parameter='T6 (Температура входа в реактор Р-202)',
                current_value=current_t6,
                recommended_value=current_t6 + temp_rise,
                delta=temp_rise,
                unit_of_measure='°C',
                energy_impact_rub_h=round(energy_cost, 0),
                additive_cost_rub_h=0.0,
                total_cost_rub_h=round(energy_cost, 0),
                explanation=(
                    f'Подъем температуры нагрева на +{temp_rise:.1f} °C снизит'
                    f' серу в ГОДТ на ~{temp_rise*0.3:.2f} мг/кг.'
                ),
            )
        )
      else:
        # Температурный ресурс исчерпан -> разгрузка по сырью F9
        feed_cut = round(feed_tph * 0.05, 1)
        candidates.append(
            ActionCandidate(
                target_unit='Гидроочистка 24-2000 (Сырьевой насос)',
                parameter='F9 (Расход сырья на установку, массовый)',
                current_value=feed_tph,
                recommended_value=feed_tph - feed_cut,
                delta=-feed_cut,
                unit_of_measure='т/ч',
                energy_impact_rub_h=12000.0,
                additive_cost_rub_h=0.0,
                total_cost_rub_h=12000.0,
                explanation=(
                    'Температурный лимит катализатора исчерпан. Снижение'
                    f' расхода сырья на -{feed_cut} т/ч для увеличения времени'
                    ' контакта.'
                ),
            )
        )

    # Сценарий 2: Коррекция вспышки (пар/газ отпарки W7 в колонну К-201)
    if qr.flash_point < self.spec.MIN_FLASH_POINT_C:
      curr_w7 = state.get('W7', 0.14)
      w7_target = curr_w7 * 1.15
      candidates.append(
          ActionCandidate(
              target_unit='Блок стабилизации (Отпарная колонна К-201)',
              parameter='W7 (Расход газа поддува на входе в К-201)',
              current_value=curr_w7,
              recommended_value=w7_target,
              delta=w7_target - curr_w7,
              unit_of_measure='т/ч',
              energy_impact_rub_h=800.0,
              additive_cost_rub_h=0.0,
              total_cost_rub_h=800.0,
              explanation=(
                  'Интенсификация отдувки легких бензиновых фракций (рост'
                  f' IBP.T) для возврата вспышки к норме >='
                  f' {self.spec.MIN_FLASH_POINT_C} °C.'
              ),
          )
      )

    return candidates