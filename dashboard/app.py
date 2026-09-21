"""
Интерактивный дашборд оператора технологической цепочки на Streamlit.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from config.settings import SPEC_K5, RESOURCES_DIR
from agents.orchestrator import Orchestrator
from models.blending_engine import BlendingEngine, BlendComponent
from data_pipeline.synchronizer import build_full_dataset

st.set_page_config(
    page_title="МАС: Оптимизация ДТ Евро-5",
    page_icon="⛽",
    layout="wide"
)

st.title("⛽ Мультиагентная система управления качеством ДТ")
st.caption("Сквозная цепочка: АВТ ➔ Гидроочистка 24-2000 ➔ Резервуарный блендинг ➔ ГОСТ 32511-2013 (К5)")

# 1. Инициализация оркестратора
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = Orchestrator()
orchestrator = st.session_state.orchestrator


# 2. Кэшированная загрузка реального датасета
@st.cache_data(show_spinner="Загрузка архива телеметрии (189 000 строк)...")
def load_cached_history():
    try:
        return build_full_dataset()
    except Exception as e:
        st.error(f"Ошибка загрузки архива: {e}")
        return None


# 3. Боковая панель
st.sidebar.header("🕹️ Режим работы дашборда")
data_mode = st.sidebar.radio(
    "Источник данных:",
    [
        "Ручной ввод установок",
        "Реальный архив телеметрии (из resources/)",
        "Демо-сценарии (быстрый показ)"
    ]
)

row = None
history_df = None
point_idx = 0

if data_mode == "Ручной ввод установок":
    st.sidebar.subheader("📊 Показатели процесса (CV / DV):")
    # ИДЕАЛЬНЫЕ ШТАТНЫЕ УСТАВКИ ПО УМОЛЧАНИЮ
    q21_in = st.sidebar.number_input("Сера ГОДТ Q21 (мг/кг)", value=7.20, step=0.10)
    p8_in = st.sidebar.number_input("Перепад dP Р-202 P8 (МПа)", value=0.22, step=0.05)
    flash_in = st.sidebar.number_input("Температура вспышки T18 (°C)", value=62.0, step=1.0)

    st.sidebar.subheader("🎛️ Управляемые переменные (MV):")
    t6_in = st.sidebar.number_input("Температура входа Р-202 T6 (°C)", value=358.0, step=0.5)
    f9_in = st.sidebar.number_input("Расход сырья ГОДТ F9 (т/ч)", value=170.0, step=5.0)
    w7_in = st.sidebar.number_input("Газ отпарки К-201 W7 (т/ч)", value=0.140, step=0.010, format="%.3f")

    # Идеальный срез для ручного режима
    row = pd.Series({
        'date': '2026-08-04 12:00:00',
        'Q21': q21_in,
        'P8': p8_in,
        'T6': t6_in,
        'T11': t6_in + 14.0,
        'T18': flash_in,
        'F9': f9_in,
        'W7': w7_in,
        'LIMS_Гидроочистка.. Точка отбора 2. Продукт Дизельное топливо_Mg.Sulfur': q21_in,
        'LIMS_Гидроочистка.. Точка отбора 2. Продукт Дизельное топливо_Mg.Sulfur__age_h': 4.0
    })

elif data_mode == "Реальный архив телеметрии (из resources/)":
    history_df = load_cached_history()

    if history_df is None or history_df.empty:
        st.sidebar.warning("Файлы архива не найдены в resources/. Переключаем в демо-режим.")
        data_mode = "Демо-сценарии (быстрый показ)"
    else:
        st.sidebar.success(f"Загружен архив: {len(history_df):,} точек")

        point_idx = st.sidebar.slider(
            "Индекс временной точки (шаг 10 мин):",
            min_value=0,
            max_value=len(history_df) - 1,
            value=min(35840, len(history_df) - 1),
            step=10
        )
        row = history_df.iloc[point_idx]
        st.sidebar.info(f"Выбрана дата: **{row['date']}**")

elif data_mode == "Демо-сценарии (быстрый показ)":
    scenario = st.sidebar.selectbox(
        "Выберите ситуацию:",
        [
            "Сценарий 1: Штатный режим (Стабильный)",
            "Сценарий 2: Риск серы (9.4 мг/кг) и вспышки",
            "Сценарий 3: Сбой датчика Q21 и устаревание ЛИМС"
        ]
    )
    if scenario == "Сценарий 1: Штатный режим (Стабильный)":
        row = pd.Series({
            'date': '2026-08-01 10:00:00',
            'Q21': 7.2,
            'P8': 0.22,
            'T6': 358.0,
            'T11': 371.0,
            'T18': 62.0,
            'F9': 170.0,
            'W7': 0.140
        })
    elif scenario == "Сценарий 2: Риск серы (9.4 мг/кг) и вспышки":
        row = pd.Series({
            'date': '2026-08-02 14:30:00',
            'Q21': 9.4,
            'P8': 0.35,
            'T6': 358.0,
            'T11': 372.0,
            'T18': 52.0,
            'F9': 170.0,
            'W7': 0.140
        })
    elif scenario == "Сценарий 3: Сбой датчика Q21 и устаревание ЛИМС":
        row = pd.Series({
            'date': '2026-08-03 18:00:00',
            'Q21': None,
            'LIMS_Гидроочистка.. Точка отбора 2. Продукт Дизельное топливо_Mg.Sulfur__age_h': 32.0,
            'P8': 0.25,
            'T6': 360.0,
            'T11': 374.0,
            'T18': 60.0,
            'F9': 170.0,
            'W7': 0.140
        })

decision = orchestrator.process_step(row)
qa_eval = orchestrator.quality_agent.evaluate(row)

current_s = qa_eval.active_sulfur
s_source = qa_eval.source

# =====================================================================
# ВЕРХНИЙ БЛОК: КАРТОЧКИ KPI
# =====================================================================
col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    if pd.notna(current_s):
        delta_val = current_s - 10.0
        st.metric(
            label=f"Сера ГОДТ [{s_source}]",
            value=f"{current_s:.2f} мг/кг",
            delta=f"{delta_val:+.2f} до лимита",
            delta_color="inverse"
        )
    else:
        st.metric(label="Сера ГОДТ", value="НЕТ ДАННЫХ", delta="ОТКАЗ / СБОЙ")

with col2:
    p8_val = row.get('P8', np.nan)
    p8_val = float(p8_val) if pd.notna(p8_val) else 0.0
    st.metric(
        label="Перепад dP Р-202",
        value=f"{p8_val:.2f} МПа",
        delta="Норма (<= 0.8 МПа)" if p8_val <= 0.8 else "КРИТИЧЕСКИЙ ПЕРЕПАД",
        delta_color="normal" if p8_val <= 0.8 else "inverse"
    )

with col3:
    flash_val = row.get('T18', np.nan)
    flash_val = float(flash_val) if pd.notna(flash_val) else qa_eval.flash_point
    st.metric(
        label="Вспышка ГОДТ",
        value=f"{flash_val:.1f} °C",
        delta="Норма (>= 55 °C)" if flash_val >= 55.0 else "НИЖЕ ГОСТ",
        delta_color="normal" if flash_val >= 55.0 else "inverse"
    )

with col4:
    t6_val = row.get('T6', np.nan)
    t6_val = float(t6_val) if pd.notna(t6_val) else 0.0
    st.metric(label="Печь T6", value=f"{t6_val:.1f} °C" if t6_val > 0 else "НЕТ ДАННЫХ")

with col5:
    f9_val = row.get('F9', np.nan)
    f9_val = float(f9_val) if pd.notna(f9_val) else 170.0
    st.metric(label="Сырье F9", value=f"{f9_val:.1f} т/ч")

with col6:
    w7_val = row.get('W7', np.nan)
    w7_val = float(w7_val) if pd.notna(w7_val) else 0.140
    st.metric(label="Газ W7", value=f"{w7_val:.3f} т/ч")

# =====================================================================
# ГРАФИК ТРЕНДА (ТОЧКА СТРОГО НА СИНЕЙ ЛИНИИ)
# =====================================================================
if history_df is not None and ('Q21' in history_df.columns or 'PAK_Sulfur' in history_df.columns):
    st.subheader("📈 Тренд серы (окно ±2 суток вокруг выбранной точки)")
    window_start = max(0, point_idx - 144)
    window_end = min(len(history_df), point_idx + 144)
    sub_df = history_df.iloc[window_start:window_end]

    sulfur_col = 'Q21' if 'Q21' in sub_df.columns else 'PAK_Sulfur'

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sub_df['date'],
        y=sub_df[sulfur_col],
        mode='lines',
        name='Сера КИП (мг/кг)',
        line=dict(color='#1f77b4', width=2)
    ))
    fig.add_hline(
        y=10.0,
        line_dash="dash",
        line_color="red",
        annotation_text="Лимит ГОСТ (10 мг/кг)"
    )

    # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: берем ровно то значение, которое нарисовано на синей линии!
    curve_point_val = row.get(sulfur_col, np.nan)
    if pd.notna(curve_point_val):
        fig.add_trace(go.Scatter(
            x=[row['date']],
            y=[curve_point_val],
            mode='markers',
            marker=dict(size=12, color='gold', symbol='diamond', line=dict(width=2, color='black')),
            name=f'Текущая точка КИП ({curve_point_val:.2f} мг/кг)'
        ))

    fig.update_layout(
        height=260,
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", y=1.1)
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# =====================================================================
# РЕШЕНИЕ ОРКЕСТРАТОРА (СТРОГО ПО ТЗ)
# =====================================================================
st.subheader("📋 Решение мультиагентной системы (МАС)")
status = decision.get("status")

if status == "NORMAL_OPERATION":
    st.success("✅ **ШТАТНЫЙ РЕЖИМ:** Процесс оптимален. Вмешательство регуляторов не требуется.")
    st.write(decision["message"])

elif status == "REFUSAL_TO_RECOMMEND":
    st.error("🛑 **РЕГЛАМЕНТНЫЙ ОТКАЗ ОТ ВЫДАЧИ РЕКОМЕНДАЦИЙ (SAFETY FALLBACK)**")
    st.warning(f"**Причина:** {decision['reason']}")
    st.info(f"**Действие для персонала:** {decision['action_required']}")

elif status == "EQUIPMENT_OVERLOAD":
    st.error("🛑 **АВАРИЙНЫЙ РЕЖИМ ОБОРУДОВАНИЯ: СРОЧНАЯ РАЗГРУЗКА РЕАКТОРА!**")
    st.warning(decision.get("reason", ""))

elif status == "CRITICAL_OFF_SPEC":
    st.error("🚨 **КРИТИЧЕСКИЙ ВЫБРОС / БРАК ПО КАЧЕСТВУ: ВЫХОД ЗА ПРЕДЕЛЫ ГОСТ!**")
    st.warning(decision.get("reason", ""))

elif status == "ENERGY_OPTIMIZATION":
    st.info("💡 **ЭНЕРГОСБЕРЕЖЕНИЕ: ОПТИМИЗАЦИЯ ТЕМПЕРАТУРЫ ПЕЧИ И БЛЕНДИНГА**")

elif status == "OPTIMIZATION_OPPORTUNITY":
    st.success("💰 **ЗОЛОТОЕ ОКНО: ВОЗМОЖНО УВЕЛИЧЕНИЕ ВЫРАБОТКИ**")

elif status == "ACTION_RECOMMENDED":
    st.warning("⚠️ **ТРЕБУЕТСЯ УПРАВЛЯЮЩЕЕ ВОЗДЕЙСТВИЕ ДЛЯ ВЫВОДА В НОРМУ**")

if status in ["ACTION_RECOMMENDED", "EQUIPMENT_OVERLOAD", "OPTIMIZATION_OPPORTUNITY", "ENERGY_OPTIMIZATION"]:
    c_left, c_right = st.columns([1, 1])

    with c_left:
        st.markdown("#### Рекомендуемый пакет воздействий:")
        act = decision.get("recommended_action", {})
        all_acts = act.get('all_actions', [])

        if all_acts:
            for a in all_acts:
                curr_v = a.get('current', 0.0)
                targ_v = a.get('target', 0.0)
                uom = a.get('unit_of_measure', '')
                fmt = ".3f" if abs(curr_v) < 1.0 else ".1f"
                st.write(f"• **{a.get('parameter', '-')}:** `{curr_v:{fmt}} {uom}` ➔ **`{targ_v:{fmt}} {uom}`** ({a.get('delta', '-')})")
        else:
            curr_v = act.get('current', 0.0)
            targ_v = act.get('target', 0.0)
            uom = act.get('unit_of_measure', '')
            fmt = ".3f" if abs(curr_v) < 1.0 else ".1f"
            st.write(f"• **{act.get('parameter', '-')}:** `{curr_v:{fmt}} {uom}` ➔ **`{targ_v:{fmt}} {uom}`** ({act.get('delta', '-')})")

        st.caption(f"Оценка экономического эффекта: **{act.get('estimated_cost', '-')}**")

    with c_right:
        st.markdown("#### Прогноз выполнения жестких ограничений:")
        for item in decision.get("constraints_verified", []):
            if isinstance(item, (tuple, list)) and len(item) == 2:
                text, passed = item
                if passed:
                    st.write(f"✔️ **{text}:** Выполнено")
                else:
                    st.write(f"❌ **{text}:** НАРУШЕНО")
            else:
                st.write(f"• {item}")

    st.markdown("#### Объяснение логики решения оператору:")
    expl_text = decision.get("explanation_for_operator", decision.get("reason", decision.get("message", "Режим требует контроля.")))

    if status in ["CRITICAL_OFF_SPEC", "EQUIPMENT_OVERLOAD"]:
        st.error(expl_text)
    elif status == "ENERGY_OPTIMIZATION":
        st.info(expl_text)
    elif status == "OPTIMIZATION_OPPORTUNITY":
        st.success(expl_text)
    else:
        st.warning(expl_text)

st.divider()

# =====================================================================
# ИНТЕРАКТИВНЫЙ БЛЕНДИНГ
# =====================================================================
st.subheader("🧪 Интерактивный резервуарный блендинг")
b_col1, b_col2, b_col3 = st.columns(3)

with b_col1:
    kero_share = st.slider("Доля Керосина (%):", min_value=0, max_value=30, value=15, step=1) / 100.0
    gasoil_share = st.slider("Доля Газойля (%):", min_value=0, max_value=15, value=0, step=1) / 100.0
    godt_share = 1.0 - kero_share - gasoil_share
    st.write(f"**Доля ГОДТ:** `{godt_share*100:.1f}%` (Баланс: 100%)")

with b_col2:
    cetane_booster = st.slider(
        "Присадка А: Цетаноповышающая (кг/т):",
        min_value=0.0,
        max_value=1.5,
        value=0.2,
        step=0.1
    )
    st.caption("1 кг/т дает +2.5 ЦЧ. Стоимость в 100 раз выше ДТ!")

with b_col3:
    sim_s = current_s if pd.notna(current_s) else 8.0
    sim_flash = flash_val if (pd.notna(flash_val) and flash_val > 0) else 60.0

    sim_blend = BlendingEngine.blend(
        c_hydro=BlendComponent("ГОДТ", godt_share, sim_s, 836.0, 51.5, sim_flash, 348.0, -16.0),
        c_kero=BlendComponent("Керосин", kero_share, 3.0, 795.0, 44.0, 48.0, 245.0, -48.0),
        c_gasoil=BlendComponent("Газойль", gasoil_share, 28.0, 865.0, 48.0, 75.0, 362.0, -4.0),
        dose_cetane_booster_kg_t=cetane_booster
    )

    st.markdown("##### Качество товарного дизеля в резервуаре:")
    s_color = "green" if sim_blend['sulfur'] <= 10.0 else "red"
    st.markdown(f"**Сера смеси:** :{s_color}[`{sim_blend['sulfur']:.2f}` мг/кг] (ГОСТ: <= 10.0)")

    c_color = "green" if sim_blend['cetane'] >= 51.0 else "red"
    st.markdown(f"**Цетановое число:** :{c_color}[`{sim_blend['cetane']:.1f}`] (ГОСТ: >= 51.0)")

    d_ok = (820.0 <= sim_blend['density'] <= 845.0)
    d_color = "green" if d_ok else "red"
    st.markdown(f"**Плотность D15:** :{d_color}[`{sim_blend['density']:.1f}` кг/м³] (ГОСТ: 820-845)")

    st.write(f"**T95 конца кипения:** `{sim_blend['t95']:.1f}` °C (ГОСТ: <= 360)")