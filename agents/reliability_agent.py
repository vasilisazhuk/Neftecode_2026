"""Агент надёжности оборудования и катализатора."""

from agents.base import ReliabilityReport
from config.settings import LIMITS
import pandas as pd


class ReliabilityAgent:

  def __init__(self):
    self.limits = LIMITS

  def evaluate(self, state: pd.Series) -> ReliabilityReport:
    p8_dp = state.get('P8', 0.22)
    t6_inlet = state.get('T6', 360.0)
    t11_outlet = state.get('T11', 372.0)
    delta_t = t11_outlet - t6_inlet

    is_safe = True
    alerts = []

    if p8_dp > self.limits.MAX_REACTOR_DP_MPA:
      is_safe = False
      alerts.append(
          f'Перепад давления P8={p8_dp:.2f} МПа превышает предел'
          f' {self.limits.MAX_REACTOR_DP_MPA} МПа! Угроза забивки катализатора.'
      )

    if t11_outlet > self.limits.MAX_BED_TEMP_C:
      is_safe = False
      alerts.append(
          f'Температура катализатора T11={t11_outlet:.1f} °C превышает лимит'
          f' {self.limits.MAX_BED_TEMP_C} °C!'
      )

    return ReliabilityReport(
        is_safe=is_safe,
        dp_reactor_p8=p8_dp,
        bed_temp_t11=t11_outlet,
        inlet_temp_t6=t6_inlet,
        delta_t=delta_t,
        alerts=alerts,
    )