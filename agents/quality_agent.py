"""
Агент контроля качества на базе обученного ML-классификатора и формул ВАК.
"""
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from config.settings import SPEC_K5, LIMITS
from agents.base import QualityReport

MODELS_PATH = Path(__file__).resolve().parent.parent / "models" / "saved_models" / "quality_model.joblib"


class DataQualityAgent:
    def __init__(self):
        self.spec = SPEC_K5
        self.limits = LIMITS
        # Загрузка обученной ML-модели (с фолбэком, если модель еще не обучена)
        if MODELS_PATH.exists():
            self.model = joblib.load(MODELS_PATH)
        else:
            self.model = None

    def evaluate(self, state: pd.Series) -> QualityReport:
        lims_col = "LIMS_Гидроочистка.. Точка отбора 2. Продукт Дизельное топливо_Mg.Sulfur"
        lims_val = state.get(lims_col, np.nan)
        lims_age = state.get(f"{lims_col}__age_h", 999.0)
        pak_val = state.get('Q21', np.nan)

        # 1. Приоритет источников качества
        if pd.notna(lims_val) and pd.notna(lims_age) and lims_age <= self.limits.LIMS_MAX_FRESHNESS_HOURS:
            source = "LIMS (Лаборатория)"
            sulfur = float(lims_val)
            source_age = float(lims_age)
            pak_avail = 1
        elif pd.notna(pak_val):
            source = "PAK (Поточный анализатор Q21)"
            sulfur = float(pak_val)
            source_age = 0.1
            pak_avail = 1
        else:
            source = "NO_FRESH_DATA"
            sulfur = 8.5
            source_age = 999.0
            pak_avail = 0

        flash = state.get('T18', 60.0)
        flash = float(flash) if pd.notna(flash) else 60.0

        # 2. ИНФЕРЕНС ML-МОДЕЛИ (Классификация состояния качества)
        features = pd.DataFrame([{
            'sulfur': sulfur,
            'flash': flash,
            'lims_age': source_age,
            'pak_available': pak_avail
        }])

        issues = []
        is_stale = False

        if self.model is not None:
            predicted_class = self.model.predict(features)[0]
            probabilities = self.model.predict_proba(features)[0]
            confidence = max(probabilities)

            if predicted_class == "STALE_DATA":
                risk_level = "CRITICAL"
                is_stale = True
                issues.append(f"ML: Выявлено устаревание данных качества (достоверность {confidence*100:.1f}%).")
            elif predicted_class == "CRITICAL_FLASH":
                risk_level = "CRITICAL"
                issues.append(f"ML: Критический риск по вспышке ({flash:.1f} °C < 55 °C, вероятность {confidence*100:.1f}%).")
            elif predicted_class == "OFF_SPEC_SULFUR":
                risk_level = "OFF_SPEC"
                issues.append(f"ML: Брак по содержанию серы ({sulfur:.2f} мг/кг > 10.0, уверенность {confidence*100:.1f}%).")
            elif predicted_class == "WARNING_SULFUR":
                risk_level = "WARNING"
                issues.append(f"ML: Предупреждение о дрейфе серы в опасную зону ({sulfur:.2f} мг/кг).")
            else:
                risk_level = "NORMAL"
        else:
            # Фолбэк на правила, если файл .joblib не найден
            risk_level = "CRITICAL" if flash < 55.0 or pak_avail == 0 else "NORMAL"
            is_stale = (pak_avail == 0)

        return QualityReport(
            active_sulfur=sulfur,
            source=source,
            source_age_hours=source_age,
            is_stale=is_stale,
            risk_level=risk_level,
            flash_point=flash,
            issues=issues
        )

    # Физические суррогатные модели сохраняются для расчета прогноза
    def predict_godt_sulfur(self, base_s: float, curr_t6: float, new_t6: float, curr_f9: float, new_f9: float) -> float:
        dt = new_t6 - curr_t6
        df_pct = (new_f9 - curr_f9) / max(curr_f9, 1.0)
        return max(base_s - (dt * 0.30) + (df_pct * 15.0), 0.5)

    def predict_godt_flash(self, curr_flash: float, curr_w7: float, new_w7: float) -> float:
        dw = new_w7 - curr_w7
        return max(curr_flash + (dw / 0.010) * 2.5, 20.0)