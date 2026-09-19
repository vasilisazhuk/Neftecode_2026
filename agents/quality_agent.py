"""
Агент контроля данных и качества (Data & Quality Guardian).
"""
import pandas as pd
import numpy as np
from config.settings import SPEC_K5, LIMITS
from agents.base import QualityReport


class DataQualityAgent:
    def __init__(self):
        self.spec = SPEC_K5
        self.limits = LIMITS

    def evaluate(self, state: pd.Series) -> QualityReport:
        lims_col = "LIMS_Гидроочистка.. Точка отбора 2. Продукт Дизельное топливо_Mg.Sulfur"
        lims_val = state.get(lims_col, np.nan)
        lims_age = state.get(f"{lims_col}__age_h", 999.0)
        pak_val = state.get('Q21', np.nan)

        source = "UNKNOWN"
        sulfur = np.nan
        is_stale = False
        source_age = 0.0

        # Иерархия истинности по ТЗ: ЛИМС -> ПАК -> отказ
        # Используем pd.notna, чтобы корректно обрабатывать и np.nan, и None
        if pd.notna(lims_val) and pd.notna(lims_age) and lims_age <= self.limits.LIMS_MAX_FRESHNESS_HOURS:
            source = "LIMS (Лаборатория)"
            sulfur = float(lims_val)
            source_age = float(lims_age)
        elif pd.notna(pak_val):
            source = "PAK (Поточный анализатор Q21)"
            sulfur = float(pak_val)
            source_age = 0.1
        else:
            source = "NO_FRESH_DATA"
            is_stale = True

        flash = state.get('T18', 60.0)

        issues = []
        risk_level = "NORMAL"

        if is_stale or pd.isna(sulfur):
            risk_level = "CRITICAL"
            issues.append("Данные серы устарели или недоступны. Управление вслепую запрещено.")
        elif sulfur > self.spec.MAX_SULFUR_MG_KG:
            risk_level = "OFF_SPEC"
            issues.append(f"Сера {sulfur:.2f} мг/кг превышает предел ГОСТ К5 (макс {self.spec.MAX_SULFUR_MG_KG})!")
        elif sulfur >= 8.5:
            risk_level = "WARNING"
            issues.append(f"Сера {sulfur:.2f} мг/кг в опасной зоне рядом с пределом {self.spec.MAX_SULFUR_MG_KG}.")

        if pd.notna(flash) and flash < self.spec.MIN_FLASH_POINT_C:
            issues.append(f"Вспышка {flash:.1f} °C ниже нормы ГОСТ (>= {self.spec.MIN_FLASH_POINT_C} °C).")
            if risk_level == "NORMAL":
                risk_level = "WARNING"

        return QualityReport(
            active_sulfur=sulfur,
            source=source,
            source_age_hours=source_age,
            is_stale=is_stale,
            risk_level=risk_level,
            flash_point=flash,
            issues=issues
        )