"""
Агент надёжности оборудования на базе обученного ML-классификатора и гидродинамики.
"""
from pathlib import Path
import joblib
import pandas as pd
from config.settings import LIMITS
from agents.base import ReliabilityReport

MODELS_PATH = Path(__file__).resolve().parent.parent / "models" / "saved_models" / "reliability_model.joblib"


class ReliabilityAgent:
    def __init__(self):
        self.limits = LIMITS
        if MODELS_PATH.exists():
            self.model = joblib.load(MODELS_PATH)
        else:
            self.model = None

    def evaluate(self, state: pd.Series) -> ReliabilityReport:
        p8_dp = float(state.get('P8', 0.22)) if pd.notna(state.get('P8')) else 0.22
        t6_inlet = float(state.get('T6', 355.0)) if pd.notna(state.get('T6')) else 355.0
        t11_outlet = float(state.get('T11', 370.0)) if pd.notna(state.get('T11')) else (t6_inlet + 15.0)
        delta_t = t11_outlet - t6_inlet

        features = pd.DataFrame([{
            'dp_p8': p8_dp,
            't6': t6_inlet,
            't11': t11_outlet
        }])

        is_safe = True
        alerts = []

        if self.model is not None:
            pred_class = self.model.predict(features)[0]
            conf = max(self.model.predict_proba(features)[0])

            if pred_class == "REACTOR_DP_OVERLOAD":
                is_safe = False
                alerts.append(f"ML: Аварийный перепад давления Р-202 (P8={p8_dp:.2f} МПа, вероятность {conf*100:.1f}%).")
            elif pred_class == "CATALYST_OVERHEAT":
                is_safe = False
                alerts.append(f"ML: Риск терморазгона/перегрева катализатора (T11={t11_outlet:.1f} °C, уверенность {conf*100:.1f}%).")
        else:
            is_safe = (p8_dp <= self.limits.MAX_REACTOR_DP_MPA and t11_outlet <= self.limits.MAX_BED_TEMP_C)

        return ReliabilityReport(
            is_safe=is_safe,
            dp_reactor_p8=p8_dp,
            bed_temp_t11=t11_outlet,
            inlet_temp_t6=t6_inlet,
            delta_t=delta_t,
            alerts=alerts
        )

    def predict_reactor_dp(self, curr_dp: float, curr_f9: float, new_f9: float) -> float:
        return curr_dp * ((new_f9 / max(curr_f9, 1.0)) ** 2)