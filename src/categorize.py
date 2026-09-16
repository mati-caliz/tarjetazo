"""Clasifica cada movimiento en una categoría y le arma un nombre descriptivo:
reglas por palabra clave primero, y un modelo de IA como fallback para comercios
que no matchean ninguna regla o que vienen con prefijo "MERPAGO*".

El fallback usa DeepSeek y, si falla, Gemini. Si no hay ninguna API configurada,
se usa un nombre limpio básico sin investigar y no se cachea ese resultado."""
import json
import logging
import os
import re

import requests

log = logging.getLogger("tarjetazo.categorize")

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
    "IA / Herramientas digitales",
    "Tecnología / Electrónica",
    "Impuestos / Intereses",
    "Otros",
]

# (patrón regex sobre el detalle en mayúsculas) -> categoría
REGLAS: list[tuple[str, str]] = [
    (
        r"MCDONALDS|BURGER|FRATELLI|HAVANNA|PICCOLO|BIMBI|CAFF?[EÉ]|CAFETERIA|"
        r"BAR\b|BULLER|CREPAS|TOSTADO|DANDY|BRASILACAI|RAPANUI|SBUX|STARBUCKS",
        "Restaurantes / Bares",
    ),
    (r"TRADE SKY BAR|SOCIALCLUB|PASSLINE|BIGBOX|CINEMA|MUNDOTICKET|EVENTOS?\b", "Entretenimiento"),
    (r"SHELL|YPF|AXION|PUMA ENERGY|GNC", "Combustible"),
    (r"WELLHUB|GYM|FITNESS", "Salud / Gimnasio"),
    (r"RAPPI|PEDIDOSYA|GLOVO", "Delivery / Apps de comida"),
    (r"SUPERMERCADO|CARREFOUR|COTO|DIA(?:\s+TIENDA|\s*%)|EXPRESS \w+ \d", "Supermercado / Almacén"),
    (r"NETFLIX|SPOTIFY|DISNEY|HBO|YOUTUBE|CLARO|PERSONAL|MOVISTAR|DIRECTV", "Servicios / Suscripciones"),
    (r"DEEPSEEK|OPENAI|CHATGPT|ANTHROPIC|CLAUDE|CURSOR|GITHUB|VERCEL", "IA / Herramientas digitales"),
    (r"GAUSSONLINE|GAUSS\s+ONLINE", "Tecnología / Electrónica"),
    (r"DB\.RG|IIBB\s+PERCEP|IVA\s+RG|INTERESES?\s+FINANCIACION", "Impuestos / Intereses"),
    (r"UBER|CABIFY|SUBE|PEAJE|ESTACIONAMIENTO|ACARREO", "Transporte"),
    (r"CENIDOR", "Indumentaria / Retail"),
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
        "(varios cobran a través de Mercado Pago, con prefijo MERPAGO*). Identificá "
        "qué es cada uno (rubro, nombre real del negocio si lo conocés) y asignale UNA "
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
        resultado = {}
        for detalle in detalles:
            info = data.get(detalle)
            if not isinstance(info, dict):
                continue
            nombre = info.get("nombre")
            categoria = info.get("categoria")
            if isinstance(nombre, str) and nombre.strip() and categoria in CATEGORIAS:
                resultado[detalle] = {"nombre": nombre.strip(), "categoria": categoria}
        return resultado
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def _investigar_con_api_compatible(
    detalles: list[str], base_url: str, api_key: str, model: str
) -> dict[str, dict[str, str]]:
    if not detalles:
        return {}

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": _prompt_investigacion(detalles)}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        timeout=60,
    )
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"]
    return _parsear_json_resultado(raw, detalles)


def investigar_con_deepseek(detalles: list[str]) -> dict[str, dict[str, str]]:
    return _investigar_con_api_compatible(
        detalles,
        os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        os.environ["DEEPSEEK_API_KEY"],
        os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
    )


def investigar_con_gemini(detalles: list[str]) -> dict[str, dict[str, str]]:
    return _investigar_con_api_compatible(
        detalles,
        os.environ.get(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
        ),
        os.environ["GEMINI_API_KEY"],
        os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"),
    )


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
        categoria_regla = categorizar_por_reglas(detalle)
        if detalle in conocidos:
            info = conocidos[detalle]
            if categoria_regla is not None and info.get("categoria") != categoria_regla:
                info = {**info, "categoria": categoria_regla, "origen": "regla"}
                conocidos[detalle] = info
                resultado[detalle] = info
            elif info.get("categoria") == "Otros" and "origen" not in info:
                conocidos.pop(detalle)
                a_investigar.append(detalle)
            else:
                resultado[detalle] = info
        elif necesita_investigacion(detalle):
            a_investigar.append(detalle)
        else:
            resultado[detalle] = {
                "nombre": detalle.title(),
                "categoria": categoria_regla,
                "origen": "regla",
            }

    investigados: dict[str, dict[str, str]] = {}
    if a_investigar:
        proveedores = []
        if os.environ.get("DEEPSEEK_API_KEY"):
            proveedores.append(investigar_con_deepseek)
        if os.environ.get("GEMINI_API_KEY"):
            proveedores.append(investigar_con_gemini)
        for investigar in proveedores:
            try:
                investigados = investigar(a_investigar)
                if investigados:
                    break
            except (requests.RequestException, KeyError, TypeError, ValueError) as error:
                log.warning("Falló el proveedor %s: %s", investigar.__name__, error)
                continue

    for detalle in a_investigar:
        investigado = investigados.get(detalle)
        info = investigado or {
            "nombre": _nombre_basico(detalle),
            "categoria": categorizar_por_reglas(detalle) or "Otros",
        }
        categoria_regla = categorizar_por_reglas(detalle)
        if categoria_regla is not None:
            info = {**info, "categoria": categoria_regla, "origen": "regla"}
        elif investigado is not None:
            info = {**info, "origen": "modelo"}
        resultado[detalle] = info
        if categoria_regla is not None or investigado is not None:
            conocidos[detalle] = info

    return resultado
