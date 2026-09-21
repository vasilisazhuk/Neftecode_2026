"""Автотесты верификации формул ВАК по эталонам из ТЗ хакатона."""

from models.vak_calculators import VAKCalculators


def test_vak_precision_official_data():
  ex_24000 = {
      'T12': 175.10,
      'F15': 2787.38,
      'W7': 0.143,
      'T23': 234.20,
      'F1': 2.613,
      'F26': 201.23,
      'P13': 3.759,
      'F9': 171.09,
      'T6': 360.13,
      'T16': 30.011,
      'F22': 10507.55,
      'P8': 0.117,
      'P24': 0.595,
      'F25': 13242.36,
  }
  # Сверка со справочником хакатона
  assert abs(VAKCalculators.godt_t90(ex_24000) - 324.92) < 0.1
  assert abs(VAKCalculators.godt_t50(ex_24000) - 263.86) < 0.1
  assert abs(VAKCalculators.godt_cfpp(ex_24000) - (-17.33)) < 0.1

  ex_avt = {
      'F65': 789.54,
      'F32': 79.00,
      'F30': 98.97,
      'T66': 255.04,
      'T33': 335.41,
      'F7': 217.54,
      'F34': 60.02,
      'F45': 16.45,
      'F59': 196.85,
      'F63': 88.16,
  }
  assert abs(VAKCalculators.avt_240_350_d15(ex_avt) - 849.83) < 0.1
  assert abs(VAKCalculators.avt_240_350_t50(ex_avt) - 271.82) < 0.1


if __name__ == '__main__':
  test_vak_precision_official_data()
  print(' Все формулы ВАК успешно прошли валидацию!')