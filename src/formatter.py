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


def _comparar_con_anterior(
    total_pesos: float, por_categoria_totales: dict[str, float], anterior: dict | None
) -> list[str]:
    if anterior is None:
        return []

    lineas = ["", "📊 <b>Vs. mes anterior</b>"]

    total_previo = anterior["total_pesos"]
    if total_previo:
        delta_pct = (total_pesos - total_previo) / total_previo * 100
        flecha = "🔺" if delta_pct > 0 else ("🔻" if delta_pct < 0 else "➖")
        lineas.append(
            f"{flecha} {abs(delta_pct):.0f}% ({_money(total_pesos)} vs {_money(total_previo)})"
        )

    categorias_previas = anterior.get("por_categoria", {})
    cambios = []
    for cat in set(por_categoria_totales) | set(categorias_previas):
        actual = por_categoria_totales.get(cat, 0.0)
        previo = categorias_previas.get(cat, 0.0)
        diff = actual - previo
        if abs(diff) >= 1:
            cambios.append((diff, cat))
    cambios.sort(key=lambda c: -abs(c[0]))

    for diff, cat in cambios[:3]:
        emoji = EMOJI_CATEGORIA.get(cat, "🔹")
        signo = "+" if diff > 0 else "−"
        lineas.append(f"   {emoji} {cat}: {signo}{_money(abs(diff))}")

    return lineas


def formatear_resumen(
    movimientos: list[Movimiento],
    info: dict[str, dict[str, str]],
    periodo: str,
    anterior: dict | None = None,
    advertencia: str | None = None,
) -> str:
    por_categoria: dict[str, list[Movimiento]] = {}
    for m in movimientos:
        cat = info.get(m.detalle, {}).get("categoria", "Otros")
        por_categoria.setdefault(cat, []).append(m)

    total_pesos = sum(m.pesos for m in movimientos)
    total_dolar = sum(m.dolar for m in movimientos)
    por_categoria_totales = {cat: sum(m.pesos for m in movs) for cat, movs in por_categoria.items()}

    lineas = [f"💳 <b>Resumen tarjeta BNA — cierre {periodo}</b>", ""]

    if advertencia:
        lineas.append(f"⚠️ {advertencia}")
        lineas.append("")

    for cat, movs in sorted(por_categoria.items(), key=lambda kv: -sum(m.pesos for m in kv[1])):
        subtotal = por_categoria_totales[cat]
        emoji = EMOJI_CATEGORIA.get(cat, "🔹")
        lineas.append(f"{emoji} <b>{cat}</b> — {_money(subtotal)}")
        for m in sorted(movs, key=lambda m: -(m.pesos or m.dolar)):
            nombre = info.get(m.detalle, {}).get("nombre", m.detalle.title())
            lineas.append(f"   • {nombre}: {_monto_movimiento(m)}")
        lineas.append("")

    lineas.append(f"💰 <b>Total: {_money(total_pesos)}</b>")
    if total_dolar:
        lineas.append(f"💵 <b>Total en dólares: {_money(total_dolar, 'U$S ')}</b>")

    lineas.extend(_comparar_con_anterior(total_pesos, por_categoria_totales, anterior))

    return "\n".join(lineas)
