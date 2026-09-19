"""Интерактивный дашборд оператора технологической цепочки на Streamlit."""
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))


from agents.orchestrator import Orchestrator
from models.blending_engine import BlendComponent, BlendingEngine
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="МАС: Оптимизация ДТ Евро-5", page_icon="⛽", layout="wide"
)

st.title("⛽ Мультиагентная система управления качеством ДТ")
st.caption(
    "Сквозная цепочка: АВТ ➔ Гидроочистка 24-2000 ➔ Резервуарный блендинг ➔"
    " ГОСТ 32511-2013 (К5)"
)

if "orchestrator" not in st.session_state:
  st.session_state.orchestrator = Orchestrator()

orchestrator = st.session_state.orchestrator

st.sidebar.header("🕹️ Управление сценарием")
scenario = st.sidebar.selectbox(
    "Выберите технологическую ситуацию:",
    [
        "Сценарий 1: Штатный режим (Стабильный)",
        "Сценарий 2: Риск серы (9.4 мг/кг) и вспышки",
        "Сценарий 3: Сбой датчика Q21 и устаревание ЛИМС",
        "Пользовательский ввод параметров",
    ],
)

if scenario == "Сценарий 1: Штатный режим (Стабильный)":
  row = pd.Series({
      "date": "2026-08-01 10:00:00",
      "Q21": 7.2,
      "P8": 0.22,
      "T6": 358.0,
      "T11": 371.0,
      "T18": 62.0,
      "F9": 170.0,
      "W7": 0.14,
  })
elif scenario == "Сценарий 2: Риск серы (9.4 мг/кг) и вспышки":
  row = pd.Series({
      "date": "2026-08-02 14:30:00",
      "Q21": 9.4,
      "P8": 0.35,
      "T6": 358.0,
      "T11": 372.0,
      "T18": 52.0,
      "F9": 170.0,
      "W7": 0.14,
  })
elif scenario == "Сценарий 3: Сбой датчика Q21 и устаревание ЛИМС":
  row = pd.Series({
      "date": "2026-08-03 18:00:00",
      "Q21": None,
      "LIMS_Гидроочистка.. Точка отбора 2. Продукт Дизельное топливо_Mg.Sulfur__age_h": (
          32.0
      ),
      "P8": 0.25,
      "T6": 360.0,
      "T11": 374.0,
      "T18": 60.0,
      "F9": 170.0,
      "W7": 0.14,
  })
else:
  st.sidebar.subheader("Ручные уставки:")
  q21_in = st.sidebar.number_input(
      "Сера ПАК Q21 (мг/кг)", value=8.8, step=0.1
  )
  p8_in = st.sidebar.number_input("Перепад dP Р-202 (МПа)", value=0.30, step=0.05)
  t6_in = st.sidebar.number_input(
      "Температура входа Р-202 (°C)", value=358.0, step=0.5
  )
  flash_in = st.sidebar.number_input(
      "Температура вспышки (°C)", value=58.0, step=1.0
  )
  row = pd.Series({
      "date": "2026-08-04 12:00:00",
      "Q21": q21_in,
      "P8": p8_in,
      "T6": t6_in,
      "T11": t6_in + 14.0,
      "T18": flash_in,
      "F9": 170.0,
      "W7": 0.14,
  })

decision = orchestrator.process_step(row)

# KPI метрики
col1, col2, col3, col4 = st.columns(4)
current_s = row.get("Q21")
with col1:
  st.metric(
      label="Сера ГОДТ (Поточный ПАК Q21)",
      value=f"{current_s:.2f} мг/кг" if pd.notna(current_s) else "НЕТ ДАННЫХ",
      delta=(
          f"{current_s - 10.0:.2f} до лимита"
          if pd.notna(current_s)
          else "ОТКАЗ ДАТЧИКА"
      ),
      delta_color="inverse",
  )

with col2:
  p8_val = row.get("P8", 0.0)
  st.metric(
      label="Перепад dP Р-202 (P8)",
      value=f"{p8_val:.2f} МПа",
      delta="Норма (<= 0.8 МПа)" if p8_val <= 0.8 else "КРИТИЧЕСКИЙ ПЕРЕПАД",
      delta_color="normal" if p8_val <= 0.8 else "inverse",
  )

with col3:
  flash_val = row.get("T18", 0.0)
  st.metric(
      label="Вспышка ГОДТ (ВАК T18)",
      value=f"{flash_val:.1f} °C",
      delta="Норма (>= 55 °C)" if flash_val >= 55.0 else "НИЖЕ ГОСТ",
      delta_color="normal" if flash_val >= 55.0 else "inverse",
  )

with col4:
  t6_val = row.get("T6", 0.0)
  st.metric(label="Температура входа Р-202 (T6)", value=f"{t6_val:.1f} °C")

st.divider()

# Решение МАС
st.subheader("📋 Решение мультиагентной системы (МАС)")
status = decision.get("status")

if status == "NORMAL_OPERATION":
  st.success("✅ **ШТАТНЫЙ РЕЖИМ:** Процесс стабилен. Вмешательство не требуется.")
  st.write(decision["message"])

elif status == "REFUSAL_TO_RECOMMEND":
  st.error("🛑 **РЕГЛАМЕНТНЫЙ ОТКАЗ ОТ ВЫДАЧИ РЕКОМЕНДАЦИЙ (SAFETY FALLBACK)**")
  st.warning(f"**Причина:** {decision['reason']}")
  st.info(f"**Действие для персонала:** {decision['action_required']}")

elif status == "ACTION_RECOMMENDED":
  st.warning(
      "⚠️ **ТРЕБУЕТСЯ УПРАВЛЯЮЩЕЕ ВОЗДЕЙСТВИЕ ДЛЯ ПРЕДОТВРАЩЕНИЯ БРАКА**"
  )
  c_left, c_right = st.columns([1, 1])

  with c_left:
    st.markdown("#### Рекомендуемое действие:")
    act = decision["recommended_action"]
    st.info(f"""
        * **Аппарат:** {act['unit']}
        * **Параметр:** `{act['parameter']}`
        * **Текущее значение:** `{act['current']:.1f}`
        * **Рекомендуемое значение:** **`{act['target']:.1f}`** ({act['delta']})
        * **Оценка затрат энергоресурсов:** `{act['estimated_cost']}`
        """)

  with c_right:
    st.markdown("#### Проверка жестких ограничений:")
    for constr in decision["constraints_verified"]:
      st.write(f"✔️ {constr}")

  st.markdown("#### Объяснение логики решения оператору:")
  st.write(decision["explanation_for_operator"])

st.divider()

# Интерактивный блендинг
st.subheader("🧪 Интерактивный резервуарный блендинг")
b_col1, b_col2, b_col3 = st.columns(3)

with b_col1:
  kero_share = (
      st.slider(
          "Доля Керосина (%):", min_value=0, max_value=30, value=15, step=1
      )
      / 100.0
  )
  gasoil_share = (
      st.slider(
          "Доля Газойля (%):", min_value=0, max_value=15, value=0, step=1
      )
      / 100.0
  )
  godt_share = 1.0 - kero_share - gasoil_share
  st.write(f"**Доля ГОДТ:** `{godt_share*100:.1f}%` (Баланс: 100%)")

with b_col2:
  cetane_booster = st.slider(
      "Присадка А: Цетаноповышающая (кг/т):",
      min_value=0.0,
      max_value=1.5,
      value=0.2,
      step=0.1,
  )
  st.caption("1 кг/т дает +2.5 ЦЧ. Стоимость в 100 раз выше ДТ!")

with b_col3:
  sim_s = current_s if pd.notna(current_s) else 8.0
  sim_blend = BlendingEngine.blend(
      c_hydro=BlendComponent("ГОДТ", godt_share, sim_s, 836.0, 51.5, 60.0, 348.0, -16.0),
      c_kero=BlendComponent("Керосин", kero_share, 3.0, 795.0, 44.0, 48.0, 245.0, -48.0),
      c_gasoil=BlendComponent("Газойль", gasoil_share, 28.0, 865.0, 48.0, 75.0, 362.0, -4.0),
      dose_cetane_booster_kg_t=cetane_booster,
  )

  st.markdown("##### Качество товарного дизеля в резервуаре:")
  st.write(
      f"**Сера смеси:** `{sim_blend['sulfur']:.2f}` мг/кг (ГОСТ: <= 10.0)"
  )
  st.write(f"**Цетановое число:** `{sim_blend['cetane']:.1f}` (ГОСТ: >= 51.0)")
  st.write(
      f"**Плотность D15:** `{sim_blend['density']:.1f}` кг/м³ (ГОСТ: 820-845)"
  )
  st.write(f"**T95 конца кипения:** `{sim_blend['t95']:.1f}` °C (ГОСТ: <= 360)")