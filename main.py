"""Главный скрипт консольной демонстрации работы МАС."""

import json
from agents.orchestrator import Orchestrator
import pandas as pd


def main():
  orchestrator = Orchestrator()

  print('=' * 75)
  print('СЦЕНАРИЙ 1: Штатный устойчивый режим (вмешательство не требуется)')
  print('=' * 75)
  step_normal = pd.Series({
      'date': '2026-08-01 10:00:00',
      'Q21': 7.1,
      'P8': 0.22,
      'T6': 358.0,
      'T11': 371.0,
      'T18': 64.0,
      'F9': 170.0,
  })
  res1 = orchestrator.process_step(step_normal)
  print(json.dumps(res1, indent=2, ensure_ascii=False))

  print('\n' + '=' * 75)
  print(
      'СЦЕНАРИЙ 2: Дрейф серы вверх (Q21=9.4 мг/кг) -> Упреждающая коррекция'
      ' печи'
  )
  print('=' * 75)
  step_warning = pd.Series({
      'date': '2026-08-02 14:30:00',
      'Q21': 9.4,
      'P8': 0.32,
      'T6': 358.0,
      'T11': 372.0,
      'T18': 62.0,
      'F9': 170.0,
      'W7': 0.14,
  })
  res2 = orchestrator.process_step(step_warning)
  print(json.dumps(res2, indent=2, ensure_ascii=False))

  print('\n' + '=' * 75)
  print(
      'СЦЕНАРИЙ 3: Отказ датчиков и устаревание данных -> Регламентный отказ'
  )
  print('=' * 75)
  step_stale = pd.Series({
      'date': '2026-08-03 18:00:00',
      'Q21': None,
      'LIMS_Гидроочистка.. Точка отбора 2. Продукт Дизельное топливо_Mg.Sulfur__age_h': (
          36.0
      ),
      'P8': 0.25,
      'T6': 360.0,
  })
  res3 = orchestrator.process_step(step_stale)
  print(json.dumps(res3, indent=2, ensure_ascii=False))


if __name__ == '__main__':
  main()