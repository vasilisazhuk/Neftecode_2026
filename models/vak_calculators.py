"""Точные аналитические формулы виртуальных анализаторов качества (ВАК)."""

from typing import Dict


class VAKCalculators:

  @staticmethod
  def godt_t90(row: Dict[str, float]) -> float:
    # 162.998 + 0.12945×T12 + 59.57×(F15/2000) + 0.00036×W7 + 0.26366×T23 − 424.72638×F1/F26
    return (
        162.998
        + 0.12945 * row['T12']
        + 59.57 * (row['F15'] / 2000.0)
        + 0.00036 * row['W7']
        + 0.26366 * row['T23']
        - 424.72638 * (row['F1'] / row['F26'])
    )

  @staticmethod
  def godt_t50(row: Dict[str, float]) -> float:
    # 44.625 + 10.0224×P13 + 0.06981×F9 + 0.471×T6
    return (
        44.625
        + 10.0224 * row['P13']
        + 0.06981 * row['F9']
        + 0.471 * row['T6']
    )

  @staticmethod
  def godt_cloud_point(row: Dict[str, float]) -> float:
    # 0.0002×F22 + 0.0021×W7 + 0.00008×F25 − 0.30656×F1 + 0.12018×T6 + 0.01916×F9 − 48.254 − 0.05249×T16 + 0.00011
    return (
        0.0002 * row['F22']
        + 0.0021 * row['W7']
        + 0.00008 * row['F25']
        - 0.30656 * row['F1']
        + 0.12018 * row['T6']
        + 0.01916 * row['F9']
        - 48.254
        - 0.05249 * row['T16']
        + 0.00011
    )

  @staticmethod
  def godt_cfpp(row: Dict[str, float]) -> float:
    # 0.22088×T23 − 102.375 − 47.75834×P8 + 0.03862×F9 + 43.60207×W7 + 43.81849×P24
    return (
        0.22088 * row['T23']
        - 102.375
        - 47.75834 * row['P8']
        + 0.03862 * row['F9']
        + 43.60207 * row['W7']
        + 43.81849 * row['P24']
    )

  @staticmethod
  def avt_240_350_d15(row: Dict[str, float]) -> float:
    # 791.22872 − 5.30294×(F65/(F32+F30)) + 0.52755×T66 − 0.15629×T33
    ratio = row['F65'] / (row['F32'] + row['F30'])
    return 791.22872 - 5.30294 * ratio + 0.52755 * row['T66'] - 0.15629 * row['T33']

  @staticmethod
  def avt_240_350_t50(row: Dict[str, float]) -> float:
    # 283.177 − 0.01685×F7 + 0.06248×F30 + 0.22048×F34 − 0.25816×F45 − 0.12159×F59 + 0.01221×F63
    return (
        283.177
        - 0.01685 * row['F7']
        + 0.06248 * row['F30']
        + 0.22048 * row['F34']
        - 0.25816 * row['F45']
        - 0.12159 * row['F59']
        + 0.01221 * row['F63']
    )