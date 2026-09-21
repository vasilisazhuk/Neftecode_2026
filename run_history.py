"""
Запуск МАС на реальных строках из исторического архива данных.
"""
import json
from agents.orchestrator import Orchestrator
from data_pipeline.synchronizer import build_full_dataset


def main():
    # 1. Загружаем и склеиваем реальные файлы из resources/
    df = build_full_dataset()

    # 2. Инициализируем МАС
    orchestrator = Orchestrator()

    # 3. Берем 1000-ю строку из реальной истории
    sample_row = df.iloc[1000]
    print(f"\nТестируем реальный момент времени: {sample_row['date']}")

    # 4. Получаем рекомендацию
    result = orchestrator.process_step(sample_row)

    # default=str гарантирует сериализацию любых типов дат и чисел
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()