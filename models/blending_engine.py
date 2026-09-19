"""Модель товарного блендинга и расчет качества смеси в резервуаре."""

from dataclasses import dataclass
from typing import Dict


@dataclass
class BlendComponent:
  name: str
  share: float  # Доля (0..1)
  sulfur: float  # мг/кг
  density: float  # кг/м3
  cetane: float  # цетановое число
  flash_point: float  # °C
  t95: float  # °C
  cfpp: float  # °C


class BlendingEngine:

  @staticmethod
  def blend(
      c_hydro: BlendComponent,
      c_kero: BlendComponent,
      c_gasoil: BlendComponent,
      dose_cetane_booster_kg_t: float = 0.0,
      dose_depressant_kg_t: float = 0.0,
  ) -> Dict[str, float]:
    total_share = c_hydro.share + c_kero.share + c_gasoil.share
    if abs(total_share - 1.0) > 1e-4:
      raise ValueError(
          f'Сумма долей компонентов блендинга должна быть 100%! Получено:'
          f' {total_share*100:.2f}%'
      )

    # Линейный баланс показателей
    sulfur = (
        c_hydro.share * c_hydro.sulfur
        + c_kero.share * c_kero.sulfur
        + c_gasoil.share * c_gasoil.sulfur
    )
    density = (
        c_hydro.share * c_hydro.density
        + c_kero.share * c_kero.density
        + c_gasoil.share * c_gasoil.density
    )
    t95 = (
        c_hydro.share * c_hydro.t95
        + c_kero.share * c_kero.t95
        + c_gasoil.share * c_gasoil.t95
    )
    flash = (
        c_hydro.share * c_hydro.flash_point
        + c_kero.share * c_kero.flash_point
        + c_gasoil.share * c_gasoil.flash_point
    )

    # Присадки: +2.5 ЦЧ на 1 кг/т; -6°C CFPP на 1 кг/т
    cetane = (
        c_hydro.share * c_hydro.cetane
        + c_kero.share * c_kero.cetane
        + c_gasoil.share * c_gasoil.cetane
        + (dose_cetane_booster_kg_t * 2.5)
    )
    cfpp = (
        c_hydro.share * c_hydro.cfpp
        + c_kero.share * c_kero.cfpp
        + c_gasoil.share * c_gasoil.cfpp
        - (dose_depressant_kg_t * 6.0)
    )

    return {
        'sulfur': round(sulfur, 2),
        'density': round(density, 1),
        'cetane': round(cetane, 1),
        'flash_point': round(flash, 1),
        't95': round(t95, 1),
        'cfpp': round(cfpp, 1),
    }