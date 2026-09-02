# Español primero · English below
# Origen: app/llm.py del sistema en produccion (fragmento: TASK_TIERS, get_model
# y _estimate_cost; se recortaron call_llm y el cliente Gemini).
# Ilustra: cada tarea declara su tier (fast/smart) en un solo lugar, y cada
# llamada estima su costo en dolares por tokens de entrada y salida. Es la base
# del presupuesto tope y del kill-switch: el gasto se mide por operacion, no al
# final del mes.
#
# --- English ---
# Source: app/llm.py from the production system (fragment: TASK_TIERS, get_model
# and _estimate_cost; call_llm and the Gemini client were trimmed).
# Shows: each task declares its tier (fast/smart) in one place, and every call
# estimates its cost in dollars from input and output tokens. It's the basis of
# the budget cap and the kill-switch: spend is measured per operation, not at
# month's end.

TASK_TIERS: dict[str, str] = {
    # fast: output corto, estructura predecible, latencia importa
    "hashtags":          "fast",
    "caption_short":     "fast",
    "clasificacion":     "fast",
    "formato_post":      "fast",
    "start_greeting":    "fast",
    "brief_diario":      "fast",

    # smart: calidad importa, contexto largo, razonamiento
    "guion_carrusel":    "smart",
    "guion_historia":    "smart",
    "estrategia":        "smart",
    "analisis_semanal":  "smart",
    "descripcion_larga": "smart",
    "ayuda_archivo":     "smart",
    "comparar_piezas":   "smart",
}

# Dict final task -> model string, construido desde env vars
TASK_MODEL: dict[str, str] = {
    task: (DEFAULT_MODEL if tier == "smart" else FAST_MODEL)
    for task, tier in TASK_TIERS.items()
}

def register_task(task: str, tier: str = "smart") -> None:
    """Registra una nueva tarea en el routing. Llamar al definir tareas nuevas."""
    TASK_TIERS[task] = tier
    TASK_MODEL[task] = DEFAULT_MODEL if tier == "smart" else FAST_MODEL


# ── Tasks inmobiliarias (Fase 3) ──────────────────────────────────────────
# ficha_propiedad NO se registra: es deterministico, sin LLM.
register_task("copy_post_propiedad",    "smart")
register_task("guion_carrusel_propiedad", "smart")
register_task("historia_propiedad",     "smart")

# ── Tasks de video (Módulo 7) ──────────────────────────────────────────────
register_task("guion_video", "smart")

# ── Tasks de ingesta (Módulo 13) ──────────────────────────────────────────
register_task("extraer_propiedad", "smart")

# ── Perfil de formato por vision (Módulo 21) ──────────────────────────────
register_task("perfil_formato", "smart")


# Precios por millon de tokens (actualizar si Anthropic cambia pricing)
_COST_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6":         {"input": 3.0,  "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    # Agregar nuevos modelos aca si se cambian las env vars
}

# ETAPA 0.6/0.7: caché de instrucciones Anthropic. La parte cacheada del prompt
# NO viene en `input_tokens`: se factura aparte, escrita a 1,25x el precio de
# entrada y leída a 0,10x. Constantes con nombre, no números sueltos.
_CACHE_WRITE_MULT = 1.25
_CACHE_READ_MULT  = 0.10

_anthropic_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv("CM_ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("[LLM] CM_ANTHROPIC_API_KEY no configurada")
        _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _anthropic_client


def get_model(task: str) -> str:
    return TASK_MODEL.get(task, DEFAULT_MODEL)


def _estimate_cost(model: str, input_tokens: int, output_tokens: int,
                   cache_read: int = 0, cache_write: int = 0) -> float:
    """Coste estimado en USD para una llamada Anthropic.

    Contabilidad de entrada con caché de instrucciones (ETAPA 0.7):
        entrada total procesada = input_tokens + cache_write + cache_read
        coste = (input * P_in
                 + cache_write * P_in * 1.25
                 + cache_read  * P_in * 0.10
                 + output * P_out) / 1_000_000

    El `response.usage.input_tokens` de Anthropic EXCLUYE la parte cacheada; si
    el cálculo no la suma con sus multiplicadores, `cost_usd` queda subestimado
    y alimenta mal la medición de coste (get_costo_pieza → tiers). cache_read /
    cache_write por palabra clave con 0 por defecto para no romper llamadores.
    """
    prices = _COST_PER_MTOK.get(model, _COST_PER_MTOK[DEFAULT_MODEL])
    p_in = prices["input"]
    return (
        input_tokens * p_in
        + cache_write * p_in * _CACHE_WRITE_MULT
        + cache_read  * p_in * _CACHE_READ_MULT
        + output_tokens * prices["output"]
    ) / 1_000_000
