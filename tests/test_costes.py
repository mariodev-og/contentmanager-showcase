"""
Costes y caché de instrucciones (BLOQUE 0-FIX).

Cubre:
- 0.7-fix: `_estimate_cost` conoce la caché (escritura 1,25x, lectura 0,10x) y
  `call_llm` devuelve los tokens de caché en el dict `usage`.
- 0.8-fix: `get_costo_pieza` / `get_costos_piezas` / `get_costos_promedio_por_tipo`
  suman los tokens de caché y toleran columnas ausentes (migration sin correr).
- 0.9-fix: `log_llm_usage` degrada con UN aviso WARN por proceso y persiste igual.

Sin red: el cliente fake es el doble del SDK; las funciones reales de
`app.supabase_client` se prueban contra el doble con get_supabase/_run parcheados.
"""

from __future__ import annotations

import pytest

import app.llm
import app.monitoring
import app.supabase_client as sb
from tests.fake_store import FakeStore, _FakeClient, _FakeQuery

MODELO = "claude-sonnet-4-6"
P_IN = 3.0
P_OUT = 15.0


# ── 0.7-fix · _estimate_cost ─────────────────────────────────────────────────

def test_estimate_cost_sin_cache():
    assert app.llm._estimate_cost(MODELO, 1_000, 2_000) == pytest.approx(
        (1_000 * P_IN + 2_000 * P_OUT) / 1_000_000
    )


def test_estimate_cost_solo_escritura():
    """Prompts equivalentes (1000 de entrada, la mitad cacheada): escribir en
    caché (1,25x) sale MÁS caro que servir todo fresco."""
    equivalente_sin_cache = app.llm._estimate_cost(MODELO, 1_000, 2_000)
    con_escritura = app.llm._estimate_cost(MODELO, 500, 2_000, cache_write=500)
    assert con_escritura == pytest.approx(
        (500 * P_IN + 500 * P_IN * app.llm._CACHE_WRITE_MULT + 2_000 * P_OUT) / 1_000_000
    )
    assert con_escritura > equivalente_sin_cache, "escribir en caché se factura más caro"


def test_estimate_cost_solo_lectura():
    """Prompts equivalentes (1000 de entrada, la mitad cacheada): leer de caché
    (0,10x) sale MÁS barato que servir todo fresco."""
    equivalente_sin_cache = app.llm._estimate_cost(MODELO, 1_000, 2_000)
    con_lectura = app.llm._estimate_cost(MODELO, 500, 2_000, cache_read=500)
    assert con_lectura == pytest.approx(
        (500 * P_IN + 500 * P_IN * app.llm._CACHE_READ_MULT + 2_000 * P_OUT) / 1_000_000
    )
    assert con_lectura < equivalente_sin_cache, "leer de caché se factura más barato"


def test_estimate_cost_mezcla():
    cost = app.llm._estimate_cost(MODELO, 400, 2_000, cache_read=300, cache_write=300)
    assert cost == pytest.approx(
        (400 * P_IN
         + 300 * P_IN * app.llm._CACHE_READ_MULT
         + 300 * P_IN * app.llm._CACHE_WRITE_MULT
         + 2_000 * P_OUT) / 1_000_000
    )


async def test_call_llm_usage_incluye_cache(monkeypatch):
    """Hallazgo D: los tokens de caché vuelven en el dict usage del llamador."""

    class _Msg:
        text = "respuesta"

    class _Usage:
        input_tokens = 100
        output_tokens = 50
        cache_read_input_tokens = 200
        cache_creation_input_tokens = 300

    class _Resp:
        content = [_Msg()]
        usage = _Usage()

    class _Messages:
        async def create(self, **kwargs):
            assert kwargs["system"][0]["cache_control"]["type"] == "ephemeral"
            return _Resp()

    class _Client:
        messages = _Messages()

    registrado: dict = {}

    def _registrar(**kw):
        registrado.update(kw)

    monkeypatch.setattr(app.llm, "_get_client", lambda: _Client())
    monkeypatch.setattr(app.llm, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(app.monitoring, "registrar_uso", _registrar)

    modelo = app.llm.get_model("guion_carrusel")
    texto, usage = await app.llm.call_llm(
        [{"role": "user", "content": "x"}], task="guion_carrusel",
        system="Identidad de marca + reglas",
    )
    assert texto == "respuesta"
    assert usage["cache_read_tokens"] == 200
    assert usage["cache_write_tokens"] == 300
    assert usage["cost_usd"] == pytest.approx(
        app.llm._estimate_cost(modelo, 100, 50, cache_read=200, cache_write=300)
    )
    assert registrado.get("cache_read_tokens") == 200
    assert registrado.get("cache_write_tokens") == 300


# ── clientes fake con/sin columnas de caché ──────────────────────────────────

class _Q(_FakeQuery):
    """Simula una DB sin las columnas de caché: falla si se usan."""

    def execute(self):
        if any("cache_read_tokens" in c for c in self._cols):
            raise RuntimeError('column "cache_read_tokens" does not exist')
        return super().execute()

    def insert(self, rows):
        data = rows if isinstance(rows, list) else [rows]
        if any("cache_read_tokens" in r for r in data):
            raise RuntimeError('column "cache_read_tokens" does not exist')
        return super().insert(rows)


class _ClienteSinCache(_FakeClient):
    def table(self, name):
        return _Q(self._store, name)


@pytest.fixture
def sb_real(monkeypatch):
    """app.supabase_client con las funciones REALES contra el doble normal."""
    store = FakeStore()
    monkeypatch.setattr(sb, "get_supabase", store.get_supabase)
    monkeypatch.setattr(sb, "_run", store._run)
    return store


@pytest.fixture
def sb_real_sin_cache(monkeypatch):
    """Idem pero la DB no tiene las columnas de caché (migración sin correr)."""
    store = FakeStore()
    monkeypatch.setattr(sb, "get_supabase", lambda: _ClienteSinCache(store))
    monkeypatch.setattr(sb, "_run", store._run)
    return store


# ── 0.8-fix · get_costo_pieza ────────────────────────────────────────────────

async def test_get_costo_pieza_con_cache(sb_real):
    await sb_real.log_llm_usage("anthropic", MODELO, "carrusel_propiedad",
                                input_tokens=100, output_tokens=50, cost_usd=0.01,
                                piece_id="p1", cache_read_tokens=200, cache_write_tokens=300)
    res = await sb.get_costo_pieza("p1")
    assert res["tokens"] == 100 + 50 + 200 + 300, "tokens = input+output+cache"
    assert res["cost_usd"] == pytest.approx(0.01)


async def test_get_costo_pieza_sin_columnas(sb_real_sin_cache):
    await sb_real_sin_cache.log_llm_usage("anthropic", MODELO, "carrusel_propiedad",
                                          input_tokens=100, output_tokens=50, cost_usd=0.01,
                                          piece_id="p1", cache_read_tokens=200, cache_write_tokens=300)
    res = await sb.get_costo_pieza("p1")
    assert res["tokens"] == 150, "sin columnas devuelve el total de siempre (sin caché)"
    assert res["cost_usd"] == pytest.approx(0.01)


async def test_get_costos_piezas_con_cache(sb_real):
    await sb_real.log_llm_usage("anthropic", MODELO, "carrusel_propiedad",
                                input_tokens=10, output_tokens=20, cost_usd=0.001,
                                piece_id="p1", cache_read_tokens=30, cache_write_tokens=40)
    res = await sb.get_costos_piezas(["p1", "p2"])
    assert res["p1"]["tokens"] == 100, "tokens = input+output+cache"
    assert res["p2"]["tokens"] == 0
    assert res["p1"]["cost_usd"] == pytest.approx(0.001)


async def test_get_costos_piezas_sin_columnas(sb_real_sin_cache):
    await sb_real_sin_cache.log_llm_usage("anthropic", MODELO, "carrusel_propiedad",
                                          input_tokens=10, output_tokens=20, cost_usd=0.001,
                                          piece_id="p1", cache_read_tokens=30, cache_write_tokens=40)
    res = await sb.get_costos_piezas(["p1"])
    assert res["p1"]["tokens"] == 30, "sin columnas devuelve el total de siempre"


async def test_get_costos_promedio_por_tipo_con_cache(sb_real):
    await sb_real.log_llm_usage("anthropic", MODELO, "carrusel_propiedad",
                                input_tokens=10, output_tokens=20, cost_usd=0.001,
                                piece_id="p1", cache_read_tokens=30, cache_write_tokens=40)
    res = await sb.get_costos_promedio_por_tipo()
    assert "carrusel prop." in res
    assert res["carrusel prop."]["tokens"] == pytest.approx(100.0)


async def test_get_costos_promedio_por_tipo_sin_columnas(sb_real_sin_cache):
    await sb_real_sin_cache.log_llm_usage("anthropic", MODELO, "carrusel_propiedad",
                                          input_tokens=10, output_tokens=20, cost_usd=0.001,
                                          piece_id="p1", cache_read_tokens=30, cache_write_tokens=40)
    res = await sb.get_costos_promedio_por_tipo()
    assert res["carrusel prop."]["tokens"] == pytest.approx(30.0), "sin columnas, total de siempre"


# ── 0.9-fix · log_llm_usage degrada con aviso único ──────────────────────────

async def test_log_llm_usage_aviso_unico(sb_real_sin_cache, capsys, monkeypatch):
    monkeypatch.setattr(sb, "_log_llm_cache_warned", False)
    for _ in range(3):
        await sb.log_llm_usage("anthropic", MODELO, "carrusel_propiedad",
                               input_tokens=1, output_tokens=2, cost_usd=0.001,
                               piece_id="p1", cache_read_tokens=5, cache_write_tokens=7)
    out = capsys.readouterr().out
    assert out.count("WARN") == 1, "exactamente un aviso por proceso"
    assert "migration_llm_cache.sql" in out
    rows = sb_real_sin_cache._select("llm_usage")
    assert len(rows) == 3, "el consumo se persiste igual aunque falten las columnas"
    assert rows[0]["input_tokens"] == 1