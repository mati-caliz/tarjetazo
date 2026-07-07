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


def _money(n: float, simbolo: str = "$") -> str:
    return f"{simbolo}{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _monto_movimiento(m: Movimiento) -> str:
    if m.dolar:
        return _money(m.dolar, "U$S ")
    return _money(m.pesos)


def formatear_resumen(movimientos: list[Movimiento], info: dict[str, dict[str, str]], periodo: str) -> str:
    por_categoria: dict[str, list[Movimiento]] = {}
    for m in movimientos:
        cat = info.get(m.detalle, {}).get("categoria", "Otros")
        por_categoria.setdefault(cat, []).append(m)

    total_pesos = sum(m.pesos for m in movimientos)
    total_dolar = sum(m.dolar for m in movimientos)

    lineas = [f"💳 <b>Resumen tarjeta BNA — cierre {periodo}</b>", ""]

    for cat, movs in sorted(por_categoria.items(), key=lambda kv: -sum(m.pesos for m in kv[1])):
        subtotal = sum(m.pesos for m in movs)
        emoji = EMOJI_CATEGORIA.get(cat, "🔹")
        lineas.append(f"{emoji} <b>{cat}</b> — {_money(subtotal)}")
        for m in sorted(movs, key=lambda m: -(m.pesos or m.dolar)):
            nombre = info.get(m.detalle, {}).get("nombre", m.detalle.title())
            lineas.append(f"   • {nombre}: {_monto_movimiento(m)}")
        lineas.append("")

    lineas.append(f"💰 <b>Total: {_money(total_pesos)}</b>")
    if total_dolar:
        lineas.append(f"💵 <b>Total en dólares: {_money(total_dolar, 'U$S ')}</b>")
    return "\n".join(lineas)
