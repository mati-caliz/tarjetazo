"""Arma el mensaje de Telegram con el resumen de gastos agrupado por categoría."""
from pdf_parser import Movimiento

EMOJI_CATEGORIA = {
    "Supermercado / Almacén": "🛒",
    "Restaurantes / Bares": "🍽️",
    "Combustible": "⛽",
    "Delivery / Apps de comida": "🛵",
    "Salud / Gimnasio": "💪",
    "Servicios / Suscripciones": "📱",
    "Transporte": "🚕",
    "Indumentaria / Retail": "👕",
    "Entretenimiento": "🎉",
    "Otros": "🔹",
}


def _money(n: float) -> str:
    return f"${n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatear_resumen(movimientos: list[Movimiento], categorias: dict[str, str], periodo: str) -> str:
    por_categoria: dict[str, list[Movimiento]] = {}
    for m in movimientos:
        cat = categorias.get(m.detalle, "Otros")
        por_categoria.setdefault(cat, []).append(m)

    total = sum(m.pesos for m in movimientos)

    lineas = [f"💳 <b>Resumen tarjeta BNA — cierre {periodo}</b>", ""]

    for cat, movs in sorted(por_categoria.items(), key=lambda kv: -sum(m.pesos for m in kv[1])):
        subtotal = sum(m.pesos for m in movs)
        emoji = EMOJI_CATEGORIA.get(cat, "🔹")
        lineas.append(f"{emoji} <b>{cat}</b> — {_money(subtotal)}")
        for m in sorted(movs, key=lambda m: -m.pesos):
            lineas.append(f"   • {m.detalle.title()}: {_money(m.pesos)}")
        lineas.append("")

    lineas.append(f"💰 <b>Total: {_money(total)}</b>")
    return "\n".join(lineas)
