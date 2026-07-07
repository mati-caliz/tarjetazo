"""Clasifica cada movimiento en una categoría y le arma un nombre descriptivo:
reglas por palabra clave primero, y Claude (con búsqueda web) como fallback para
comercios que no matchean ninguna regla o que vienen con prefijo "MERPAGO*".

Para el fallback con IA se prioriza el CLI de Claude Code (`claude -p` con la
herramienta WebSearch habilitada), que si está logueado con una suscripción
Pro/Max consume la cuota del plan en vez de facturar por token vía API. Si el
CLI no está disponible, cae a la API con ANTHROPIC_API_KEY (sin búsqueda web).
Si tampoco hay API key, se usa un nombre limpio básico sin investigar."""
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
    (r"MCDONALDS|BURGER|FRATELLI|HAVANNA|PICCOLO|BIMBI|CAFF[EÉ]|BAR\b", "Restaurantes / Bares"),
    (r"TRADE SKY BAR|SOCIALCLUB", "Entretenimiento"),
    (r"SHELL|YPF|AXION|PUMA ENERGY|GNC", "Combustible"),
    (r"WELLHUB|GYM|FITNESS", "Salud / Gimnasio"),
    (r"RAPPI|PEDIDOSYA|GLOVO", "Delivery / Apps de comida"),
    (r"SUPERMERCADO|CARREFOUR|COTO|DIA %|EXPRESS \w+ \d", "Supermercado / Almacén"),
    (r"NETFLIX|SPOTIFY|DISNEY|HBO|YOUTUBE|CLARO|PERSONAL|MOVISTAR|DIRECTV", "Servicios / Suscripciones"),
    (r"UBER|CABIFY|SUBE|PEAJE|ESTACIONAMIENTO", "Transporte"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), c) for p, c in REGLAS]

_MERPAGO_RE = re.compile(r"^MERPAGO\*", re.IGNORECASE)


def categorizar_por_reglas(detalle: str) -> str | None:
    for pattern, categoria in _COMPILED:
        if pattern.search(detalle):
            return categoria
    return None


def necesita_investigacion(detalle: str) -> bool:
    """Un comercio necesita que Claude lo investigue si no matchea ninguna regla,
    o si viene con el prefijo genérico MERPAGO* (para reemplazarlo por un nombre real)."""
    return categorizar_por_reglas(detalle) is None or bool(_MERPAGO_RE.match(detalle))


def _nombre_basico(detalle: str) -> str:
    """Limpieza sin IA: saca el prefijo MERPAGO* y titlecasea."""
    sin_prefijo = _MERPAGO_RE.sub("", detalle)
    return f"Mercado Pago: {sin_prefijo.title()}" if sin_prefijo != detalle else detalle.title()


def _prompt_investigacion(detalles: list[str]) -> str:
    return (
        "Estos son nombres de comercio de un resumen de tarjeta de crédito argentina "
        "(varios cobran a través de Mercado Pago, con prefijo MERPAGO*). Buscá en la web "
        "qué es cada uno (rubro, nombre real del negocio si lo encontrás) y asignale UNA "
        "categoría exacta de esta lista:\n"
        f"{', '.join(CATEGORIAS)}\n\n"
        "Comercios:\n" + "\n".join(f"- {d}" for d in detalles) + "\n\n"
        "Para cada uno devolvé un nombre corto y descriptivo (sin el prefijo MERPAGO*, "
        "en su lugar indicá 'Mercado Pago' si no identificás el negocio real) y la categoría.\n"
        "Respondé SOLO con un JSON válido, sin texto adicional ni markdown, con esta forma:\n"
        '{"nombre_original_del_comercio": {"nombre": "nombre descriptivo", "categoria": "categoria"}, ...}\n'
        "Usá exactamente el mismo texto de comercio de la lista como key."
    )


def _extraer_json(raw: str) -> str | None:
    """Claude a veces rodea el JSON con prosa o fuentes ('Sources: ...'). Busca el
    primer bloque {...} balanceado en vez de asumir que el texto es JSON puro."""
    inicio = raw.find("{")
    if inicio == -1:
        return None
    profundidad = 0
    for i in range(inicio, len(raw)):
        if raw[i] == "{":
            profundidad += 1
        elif raw[i] == "}":
            profundidad -= 1
            if profundidad == 0:
                return raw[inicio : i + 1]
    return None


def _parsear_json_resultado(raw: str, detalles: list[str]) -> dict[str, dict[str, str]]:
    bloque = _extraer_json(raw)
    if bloque is None:
        return {}
    try:
        data = json.loads(bloque)
        return {
            d: {"nombre": data[d]["nombre"], "categoria": data[d]["categoria"]}
            for d in detalles
            if d in data
        }
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def investigar_con_claude_cli(detalles: list[str]) -> dict[str, dict[str, str]]:
    """Usa el CLI de Claude Code con WebSearch para identificar comercios y categorizarlos.
    Si está logueado con una suscripción Pro/Max, consume la cuota del plan."""
    if not detalles:
        return {}

    prompt = _prompt_investigacion(detalles)
    resultado = subprocess.run(
        ["claude", "-p", prompt, "--allowedTools", "WebSearch", "--output-format", "text"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"claude CLI falló: {resultado.stderr.strip()}")

    return _parsear_json_resultado(resultado.stdout, detalles)


def investigar_con_claude_api(detalles: list[str]) -> dict[str, dict[str, str]]:
    """Pide a la API de Claude que categorice (sin búsqueda web). Requiere ANTHROPIC_API_KEY."""
    if not detalles:
        return {}

    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": _prompt_investigacion(detalles)}],
    )
    return _parsear_json_resultado(resp.content[0].text, detalles)


def categorizar_movimientos(
    detalles: list[str], conocidos: dict[str, dict[str, str]] | None = None
) -> dict[str, dict[str, str]]:
    """Devuelve dict detalle -> {"nombre": str, "categoria": str} para cada detalle dado.

    `conocidos` es un cache opcional (detalle -> info) de comercios ya investigados en
    corridas anteriores: si un detalle ya está ahí, no se vuelve a mandar a Claude. El
    dict se muta in-place agregando los comercios nuevos que se investiguen en esta corrida,
    para que el caller lo persista y sirva de cache la próxima vez."""
    conocidos = conocidos if conocidos is not None else {}
    resultado: dict[str, dict[str, str]] = {}
    a_investigar: list[str] = []

    for detalle in detalles:
        if detalle in conocidos:
            resultado[detalle] = conocidos[detalle]
        elif necesita_investigacion(detalle):
            a_investigar.append(detalle)
        else:
            resultado[detalle] = {"nombre": detalle.title(), "categoria": categorizar_por_reglas(detalle)}

    investigados: dict[str, dict[str, str]] = {}
    if a_investigar:
        try:
            if shutil.which("claude"):
                investigados = investigar_con_claude_cli(a_investigar)
            elif os.environ.get("ANTHROPIC_API_KEY"):
                investigados = investigar_con_claude_api(a_investigar)
        except (subprocess.TimeoutExpired, RuntimeError):
            investigados = {}

    for detalle in a_investigar:
        info = investigados.get(detalle) or {
            "nombre": _nombre_basico(detalle),
            "categoria": categorizar_por_reglas(detalle) or "Otros",
        }
        resultado[detalle] = info
        conocidos[detalle] = info

    return resultado
