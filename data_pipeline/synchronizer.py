"""
Синхронизация временных рядов с защитой от заглядывания в будущее (лаг ЛИМС 4 ч).
Устраняет коллизии имён между АВТ и 24-2000, гарантируя сохранение канонических тегов КИП.
"""
import warnings
from pathlib import Path
import pandas as pd
from config.settings import LIMITS, RESOURCES_DIR
from data_pipeline.parser import parse_russian_dates, clean_numeric


def load_telemetry(path_avt: str, path_242000: str) -> pd.DataFrame:
    """
    Склейка телеметрии: тегам АВТ дается префикс 'AVT_',
    а теги гидроочистки 24-2000 остаются в каноническом виде (T6, P8, F9, T11, T18 и др.).
    """
    print("1/3 Загрузка телеметрии АВТ и 24-2000...")
    avt = pd.read_csv(path_avt, parse_dates=['date']).sort_values('date')
    hdt = pd.read_csv(path_242000, parse_dates=['date']).sort_values('date')

    # Добавляем префикс ко всем колонкам АВТ (кроме date), чтобы избежать коллизий _x/_y
    avt_renamed = avt.rename(columns={col: f"AVT_{col}" for col in avt.columns if col != 'date'})

    # Склеиваем по временной метке date (окно 2 минуты)
    # Ставим hdt первым, чтобы сохранить чистые имена тегов гидроочистки
    return pd.merge_asof(
        hdt,
        avt_renamed,
        on='date',
        direction='nearest',
        tolerance=pd.Timedelta('2min')
    )


def attach_pak_stream(df_telemetry: pd.DataFrame, path_pak: str) -> pd.DataFrame:
    """
    Подключение поточных анализаторов серы и плотности из файла ПАК.
    Заполняет или дополняет оперативный тег Q21.
    """
    print("2/3 Обработка поточного анализатора ПАК...")
    raw = pd.read_excel(path_pak, header=None)

    # Сера в гидроочищенном ДТ
    pak_s = raw.iloc[2:, [0, 1]].copy()
    pak_s.columns = ['date', 'PAK_Sulfur']
    pak_s['date'] = parse_russian_dates(pak_s['date'])
    pak_s['PAK_Sulfur'] = clean_numeric(pak_s['PAK_Sulfur'])
    pak_s = pak_s.dropna().sort_values('date')

    # Расчётная плотность D15
    pak_d = raw.iloc[2:, [3, 4]].copy()
    pak_d.columns = ['date', 'PAK_D15']
    pak_d['date'] = parse_russian_dates(pak_d['date'])
    pak_d['PAK_D15'] = clean_numeric(pak_d['PAK_D15'])
    pak_d = pak_d.dropna().sort_values('date')

    merged_pak = pd.merge(pak_s, pak_d, on='date', how='outer').sort_values('date')

    df_res = pd.merge_asof(
        df_telemetry,
        merged_pak,
        on='date',
        direction='backward',
        tolerance=pd.Timedelta('2h')
    )

    # Гарантируем наличие и наполненность ключевого тега Q21 (сера на выходе)
    if 'Q21' in df_res.columns:
        df_res['Q21'] = df_res['Q21'].fillna(df_res['PAK_Sulfur'])
    else:
        df_res['Q21'] = df_res['PAK_Sulfur']

    return df_res


def attach_lims_with_4h_lag(df_current: pd.DataFrame, path_lims: str) -> pd.DataFrame:
    """
    Парсинг файла ЛИМС и подтягивание анализов со сдвигом на +4 часа
    (физическое время доставки пробы в лабораторию и выполнения испытания).
    """
    print("3/3 Обработка лаборатории ЛИМС (с физическим лагом 4 часа)...")
    raw = pd.read_excel(path_lims, header=None)
    installations = raw.iloc[0].ffill()

    result = df_current.copy().sort_values('date')

    # Подавляем служебное предупреждение о фрагментации памяти при добавлении 50+ колонок
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=pd.errors.PerformanceWarning)

        for i in range(0, raw.shape[1], 2):
            param_val = raw.iloc[1, i]
            if pd.isna(param_val) or str(param_val).strip() in ['', 'nan']:
                continue

            inst_name = str(installations[i]).replace("Установка '", "").replace("'", "").strip()
            col_name = f"LIMS_{inst_name}_{str(param_val).strip()}"

            part = raw.iloc[4:, [i, i+1]].copy()
            part.columns = ['date', col_name]
            part['date'] = parse_russian_dates(part['date'])
            part[col_name] = clean_numeric(part[col_name])
            part = part.dropna(subset=['date', col_name]).sort_values('date')

            if part.empty:
                continue

            # КЛЮЧЕВОЙ МОМЕНТ: результат анализа доступен системе только через 4 часа после отбора!
            part['available_at'] = part['date'] + pd.Timedelta(hours=LIMITS.LAB_REPORTING_DELAY_HOURS)
            part['sample_date'] = part['date']
            part = part.drop(columns=['date']).sort_values('available_at')

            result = pd.merge_asof(
                result,
                part,
                left_on='date',
                right_on='available_at',
                direction='backward'
            )

            # Индивидуальный возраст каждого анализа с момента взятия пробы
            result[f"{col_name}__age_h"] = (result['date'] - result['sample_date']).dt.total_seconds() / 3600.0
            result.drop(columns=['available_at', 'sample_date'], inplace=True)

    # Дефрагментируем таблицу в единый непрерывный блок памяти
    return result.copy()


def build_full_dataset() -> pd.DataFrame:
    """
    Главная функция сборки всего исторического датасета из папки resources/.
    """
    path_avt = RESOURCES_DIR / 'avt_tags.csv'
    path_242000 = RESOURCES_DIR / '242000_tags.csv'
    path_pak = RESOURCES_DIR / 'Выгрузка ПАК 01.01.2023 - н.в_.xlsx'
    path_lims = RESOURCES_DIR / 'ЛИМСы 01.01.2023 - н.в_ (2).xlsx'

    df = load_telemetry(str(path_avt), str(path_242000))
    df = attach_pak_stream(df, str(path_pak))
    df = attach_lims_with_4h_lag(df, str(path_lims))

    print(f" Датасет успешно собран! Размер: {df.shape}")
    return df