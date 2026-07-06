"""Clasifica cada movimiento en una categoría: reglas por palabra clave primero,
y Claude como fallback para comercios que no matchean ninguna regla.

Para el fallback con IA se prioriza el CLI de Claude Code (`claude -p`), que si está
logueado con una suscripción Pro/Max consume la cuota del plan en vez de facturar
por token vía API. Si el CLI no está disponible, cae a la API con ANTHROPIC_API_KEY.
Si tampoco hay API key, los comercios sin regla quedan en "Otros"."""
import json
import os
import re
import shutil
import subprocess

CATEGORIAS = [
    "Supermercado / Almacén",
    "Restaurantes / Bares",
    "Combustible",
    "Delivery / Apps de comida",
    "Salud / Gimnasio",
    "Servicios / Suscripciones",
    "Transporte",
    "Indumentaria / Retail",
    "Entretenimiento",
    "Otros",
]

# (patrón regex sobre el detalle en mayúsculas) -> categoría
REGLAS: list[tuple[str, str]] = [
    (r"MERPAGO\*MCDONALDS|MCDONALDS|BURGER|FRATELLI|HAVANNA|PICCOLO|BIMBI|CAFF[EÉ]|BAR\b", "Restaurantes / Bares"),
    (r"TRADE SKY BAR|FARANDULA|SOCIALCLUB|KOKABARTO", "Entretenimiento"),
    (r"SHELL|YPF|AXION|PUMA ENERGY|GNC", "Combustible"),
    (r"WELLHUB|GYM|FITNESS", "Salud / Gimnasio"),
    (r"RAPPI|PEDIDOSYA|GLOVO", "Delivery / Apps de comida"),
    (r"SUPERMERCADO|CARREFOUR|COTO|DIA %|EXPRESS \w+ \d", "Supermercado / Almacén"),
    (r"NETFLIX|SPOTIFY|DISNEY|HBO|YOUTUBE|CLARO|PERSONAL|MOVISTAR|DIRECTV", "Servicios / Suscripciones"),
    (r"UBER|CABIFY|SUBE|PEAJE|ESTACIONAMIENTO", "Transporte"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), c) for p, c in REGLAS]


def categorizar_por_reglas(detalle: str) -> str | None:
    for pattern, categoria in _COMPILED:
        if pattern.search(detalle):
            return categoria
    return None


def _prompt_categorizacion(detalles_sin_categoria: list[str]) -> str:
    return (
        "Clasificá cada uno de estos nombres de comercio (de un resumen de tarjeta "
        "de crédito argentino) en UNA de estas categorías exactas:\n"
        f"{', '.join(CATEGORIAS)}\n\n"
        "Comercios:\n" + "\n".join(f"- {d}" for d in detalles_sin_categoria) + "\n\n"
        "Respondé SOLO con un JSON válido: {\"nombre_comercio\": \"categoria\", ...}, "
        "usando exactamente el mismo texto de comercio como key. Sin texto adicional, sin markdown."
    )


def _parsear_json_categorias(raw: str, detalles_sin_categoria: list[str]) -> dict[str, str]:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {d: "Otros" for d in detalles_sin_categoria}


def categorizar_con_claude_cli(detalles_sin_categoria: list[str]) -> dict[str, str]:
    """Usa el CLI de Claude Code (`claude -p`) para categorizar. Si el CLI está
    logueado con una suscripción Pro/Max, esto consume la cuota del plan y no
    la API de pago por token."""
    if not detalles_sin_categoria:
        return {}

    prompt = _prompt_categorizacion(detalles_sin_categoria)
    resultado = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"claude CLI falló: {resultado.stderr.strip()}")

    return _parsear_json_categorias(resultado.stdout, detalles_sin_categoria)


def categorizar_con_claude_api(detalles_sin_categoria: list[str]) -> dict[str, str]:
    """Pide a la API de Claude que categorice. Requiere ANTHROPIC_API_KEY (pago por uso)."""
    if not detalles_sin_categoria:
        return {}

    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": _prompt_categorizacion(detalles_sin_categoria)}],
    )
    return _parsear_json_categorias(resp.content[0].text, detalles_sin_categoria)


def categorizar_movimientos(detalles: list[str]) -> dict[str, str]:
    """Devuelve dict detalle -> categoria para todos los detalles dados."""
    resultado: dict[str, str] = {}
    sin_categoria: list[str] = []

    for detalle in detalles:
        cat = categorizar_por_reglas(detalle)
        if cat:
            resultado[detalle] = cat
        else:
            sin_categoria.append(detalle)

    if sin_categoria:
        if shutil.which("claude"):
            resultado.update(categorizar_con_claude_cli(sin_categoria))
        elif os.environ.get("ANTHROPIC_API_KEY"):
            resultado.update(categorizar_con_claude_api(sin_categoria))
        else:
            for d in sin_categoria:
                resultado[d] = "Otros"

    return resultado
