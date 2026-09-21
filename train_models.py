"""
Генератор Physics-Informed датасета и обучение ML-моделей агентов.
Запуск: python train_models.py
"""
import numpy as np
import pandas as pd
from pathlib import Path
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import classification_report
from config.settings import SPEC_K5, LIMITS

MODELS_DIR = Path(__file__).resolve().parent / "models" / "saved_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

np.random.seed(42)
N_SAMPLES = 30_000

print(f"1. Генерация сбалансированного датасета цифрового двойника ({N_SAMPLES} сценариев)...")

# Генерируем равномерные диапазоны по физике процессов:
sulfur = np.random.uniform(3.0, 22.0, N_SAMPLES)
dp_p8 = np.random.uniform(0.10, 2.50, N_SAMPLES)
flash = np.random.uniform(30.0, 75.0, N_SAMPLES)
t6 = np.random.uniform(345.0, 385.0, N_SAMPLES)
t11 = t6 + np.random.uniform(8.0, 22.0, N_SAMPLES)
f9 = np.random.uniform(120.0, 225.0, N_SAMPLES)
w7 = np.random.uniform(0.080, 0.250, N_SAMPLES)
lims_age = np.random.uniform(0.5, 45.0, N_SAMPLES)
pak_available = np.random.choice([1, 0], size=N_SAMPLES, p=[0.90, 0.10])

# =====================================================================
# РАЗМЕТКА ЦЕЛЕВЫХ КЛАССОВ ПО ТЕХНОЛОГИЧЕСКИМ ПРАВИЛАМ (GROUND TRUTH)
# =====================================================================

# 1. Разметка для Quality Agent:
quality_target = []
for s, fl, age, pak in zip(sulfur, flash, lims_age, pak_available):
    if pak == 0 and age > LIMITS.LIMS_MAX_FRESHNESS_HOURS:
        quality_target.append("STALE_DATA")
    elif fl < SPEC_K5.MIN_FLASH_POINT_C:
        quality_target.append("CRITICAL_FLASH")
    elif s > SPEC_K5.MAX_SULFUR_MG_KG:
        quality_target.append("OFF_SPEC_SULFUR")
    elif s >= 8.5:
        quality_target.append("WARNING_SULFUR")
    else:
        quality_target.append("NORMAL_QUALITY")

# 2. Разметка для Reliability Agent:
reliability_target = []
for dp, t_out in zip(dp_p8, t11):
    if dp > LIMITS.MAX_REACTOR_DP_MPA:
        reliability_target.append("REACTOR_DP_OVERLOAD")
    elif t_out > LIMITS.MAX_BED_TEMP_C:
        reliability_target.append("CATALYST_OVERHEAT")
    else:
        reliability_target.append("EQUIPMENT_SAFE")

# 3. Разметка для Action Policy (Оптимизатор / Действие):
action_target = []
for q_class, r_class in zip(quality_target, reliability_target):
    if q_class == "STALE_DATA":
        action_target.append("REFUSE_SAFETY_FALLBACK")
    elif r_class == "REACTOR_DP_OVERLOAD":
        action_target.append("CUT_FEED_F9")
    elif r_class == "CATALYST_OVERHEAT":
        action_target.append("DECREASE_T6")
    elif q_class == "CRITICAL_FLASH":
        action_target.append("INCREASE_W7")
    elif q_class in ["OFF_SPEC_SULFUR", "WARNING_SULFUR"]:
        action_target.append("INCREASE_T6")
    else:
        action_target.append("STEADY_OR_THROUGHPUT_BOOST")

df_synth = pd.DataFrame({
    'sulfur': sulfur,
    'dp_p8': dp_p8,
    'flash': flash,
    't6': t6,
    't11': t11,
    'f9': f9,
    'w7': w7,
    'lims_age': lims_age,
    'pak_available': pak_available,
    'quality_target': quality_target,
    'reliability_target': reliability_target,
    'action_target': action_target
})

print(f" Распределение классов качества:\n{df_synth['quality_target'].value_counts()}\n")
print(f" Распределение классов надёжности:\n{df_synth['reliability_target'].value_counts()}\n")

# =====================================================================
# ОБУЧЕНИЕ ML-МОДЕЛЕЙ
# =====================================================================
print("2. Обучение модели Агента Качества (RandomForestClassifier)...")
X_quality = df_synth[['sulfur', 'flash', 'lims_age', 'pak_available']]
y_quality = df_synth['quality_target']
clf_quality = RandomForestClassifier(n_estimators=100, max_depth=12, random_state=42)
clf_quality.fit(X_quality, y_quality)
joblib.dump(clf_quality, MODELS_DIR / "quality_model.joblib")
print(" Модель качества сохранена.")

print("3. Обучение модели Агента Надёжности (RandomForestClassifier)...")
X_rel = df_synth[['dp_p8', 't6', 't11']]
y_rel = df_synth['reliability_target']
clf_rel = RandomForestClassifier(n_estimators=80, max_depth=10, random_state=42)
clf_rel.fit(X_rel, y_rel)
joblib.dump(clf_rel, MODELS_DIR / "reliability_model.joblib")
print(" Модель надёжности сохранена.")

print("4. Обучение модели Политики Оптимизации (Action Classifier)...")
# Модель решений учится по текущим параметрам + отчетам агентов
X_action = df_synth[['sulfur', 'flash', 'dp_p8', 't6', 't11', 'lims_age', 'pak_available']]
y_action = df_synth['action_target']
clf_action = RandomForestClassifier(n_estimators=120, max_depth=14, random_state=42)
clf_action.fit(X_action, y_action)
joblib.dump(clf_action, MODELS_DIR / "action_policy_model.joblib")
print(" Модель оптимизатора сохранена.")

print(f"\n Обучение завершено! Все модели готовы в папке: {MODELS_DIR}")