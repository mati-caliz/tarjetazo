"""Persiste el histórico de resúmenes ya procesados (total y gasto por categoría de
cada período) para poder comparar mes a mes y ver tendencias."""
import json
import os

HISTORICO_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "historico.json")


def cargar_historico() -> list[dict]:
    if not os.path.exists(HISTORICO_PATH):
        return []
    with open(HISTORICO_PATH) as f:
        return json.load(f)


def guardar_historico(historico: list[dict]) -> None:
    os.makedirs(os.path.dirname(HISTORICO_PATH), exist_ok=True)
    with open(HISTORICO_PATH, "w") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def periodo_anterior(historico: list[dict]) -> dict | None:
    """El último período registrado (llamar ANTES de agregar el período actual)."""
    return historico[-1] if historico else None


def registrar_periodo(
    historico: list[dict],
    periodo: str,
    total_pesos: float,
    total_dolar: float,
    por_categoria: dict[str, float],
) -> None:
    """Agrega el período actual al histórico (reemplaza si ya existía). Muta in-place."""
    historico[:] = [h for h in historico if h["periodo"] != periodo]
    historico.append(
        {
            "periodo": periodo,
            "total_pesos": total_pesos,
            "total_dolar": total_dolar,
            "por_categoria": por_categoria,
        }
    )
