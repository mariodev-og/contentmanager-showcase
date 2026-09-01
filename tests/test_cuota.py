"""
Cuota por cuenta (ETAPA 3.1).

Escenario de normas.md §7.2: `cuota_agotada_no_bloquea_a_otros` — alfa agota su
cuota, beta sigue generando. Y `cliente_sin_coste_ia`: el motivo que ve el
cliente se expresa en piezas/tokens, nunca en dinero.
"""

from __future__ import annotations

import pytest

import app.planes as planes
from app.job_queue import KIND_GENERAR_CARRUSEL_PROP, enqueue
from app.monitoring import puede_generar
from tests.conftest import ALFA, BETA

pytestmark = pytest.mark.cuota

_MODELO = "claude-sonnet-4-6"


async def _agotar_alfa(store, monkeypatch):
    """alfa con plan base y su cuota de piezas agotada."""
    monkeypatch.setitem(planes.CUOTAS["base"], "piezas_mes", 2)
    await store.set_brand_fields(ALFA, {"plan": "base"})
    for i in range(2):
        await store.log_llm_usage("anthropic", _MODELO, "carrusel_propiedad",
                                  input_tokens=10, output_tokens=10, cost_usd=0.0001,
                                  account_id=ALFA, piece_id=f"pieza_{i}")


async def test_cuota_agotada_no_bloquea_a_otros(app_test, store, monkeypatch):
    await _agotar_alfa(store, monkeypatch)

    ok_alfa, motivo_alfa = await puede_generar(ALFA)
    assert ok_alfa is False, "alfa sin cuota no puede generar"
    assert motivo_alfa, "debe haber un motivo"
    ok_beta, _ = await puede_generar(BETA)
    assert ok_beta is True, "beta con cuota genera con normalidad"

    # enqueue: alfa sin cuota NO encola; beta sí. La cola de beta no se frena.
    jobs_antes = len(store.tables["jobs"])
    res_alfa = await enqueue(ALFA, KIND_GENERAR_CARRUSEL_PROP, "Alfa", {"property_id": "p1"})
    assert res_alfa is None, "alfa sin cuota no encola"
    assert len(store.tables["jobs"]) == jobs_antes, "no quedan jobs de alfa"

    res_beta = await enqueue(BETA, KIND_GENERAR_CARRUSEL_PROP, "Beta", {"property_id": "p2"})
    assert res_beta is not None, "beta encola con normalidad aunque alfa esté agotada"


async def test_cliente_sin_coste_ia(app_test, store, monkeypatch):
    """El motivo de la cuota se enseña en piezas/tokens, nunca en dinero."""
    await _agotar_alfa(store, monkeypatch)
    ok, motivo = await puede_generar(ALFA)
    assert ok is False
    assert "piezas" in motivo or "tokens" in motivo
    for simbolo in ("$", "€", "USD", "céntimos", "coste"):
        assert simbolo not in motivo, f"el motivo no puede llevar dinero: {simbolo!r}"