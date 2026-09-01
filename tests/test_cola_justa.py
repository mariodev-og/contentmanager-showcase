"""
Cola justa entre cuentas (ETAPA 3.5).

Garantías de concurrencia que no se ven leyendo el código: reparto por cuenta,
tope por cuenta, race de workers y freno pesado. IMPORTANTE (lección ETAPA 3):
cada prueba verifica primero que los trabajos EXISTEN de verdad en el almacén —
una prueba de cola que pase con la cola vacía no prueba nada.
"""

from __future__ import annotations

import asyncio

import pytest

import app.job_queue as jq
from app.job_queue import KIND_GENERAR_CARRUSEL_PROP, KIND_GENERAR_VIDEO, MAX_POR_CUENTA, enqueue

pytestmark = pytest.mark.cuota


async def _encolar(account_id: str, label: str, n: int = 1) -> list[str]:
    ids = []
    for i in range(n):
        jid = await enqueue(account_id, KIND_GENERAR_CARRUSEL_PROP, f"{label}{i}", {})
        assert jid, f"enqueue de {label}{i} no devolvió id — el doble no creó el job"
        ids.append(jid)
    return ids


async def test_una_cuenta_no_bloquea_a_otra(app_test, store):
    """Escenario de Mario: A encola 5, B encola 1; el de B sale antes de que
    terminen los 5 de A (reparto justo por cuenta)."""
    ids_a = await _encolar("A", "A", 5)
    ids_b = await _encolar("B", "B", 1)
    assert len(store._select("jobs", account_id="A", status="queued")) == 5
    assert len(store._select("jobs", account_id="B", status="queued")) == 1

    obtenidos = []
    for _ in range(4):
        j = await jq._claim_next_job()
        if j:
            obtenidos.append(j["account_id"])

    # con tope 2, A mete 2 y recién ahí entra B (sin esperar a las 5 de A)
    assert obtenidos[:2] == ["A", "A"], obtenidos
    assert "B" in obtenidos, "la de B empieza sin esperar a las 5 de A"
    # quedan 3 de A en queued sin tocar
    assert len(store._select("jobs", account_id="A", status="queued")) == 3


async def test_diez_cuentas_en_paralelo(app_test, store):
    """Diez cuentas con una pieza cada una: las diez pasan a running."""
    for i in range(10):
        await _encolar(f"cuenta_{i}", f"c{i}", 1)
    assert len(store.tables["jobs"]) == 10

    reclamados = []
    for _ in range(10):
        j = await jq._claim_next_job()
        if j:
            reclamados.append(j["id"])
    assert len(reclamados) == 10, "las diez cuentas pasan a running"

    running = store._select("jobs", status="running")
    assert len({r["account_id"] for r in running}) == 10, "una running por cuenta"


async def test_tope_por_cuenta(app_test, store):
    """Una cuenta con 5 encoladas nunca supera MAX_POR_CUENTA en running."""
    await _encolar("A", "A", 5)
    assert len(store.tables["jobs"]) == 5

    reclamados = []
    for _ in range(5):
        j = await jq._claim_next_job()
        if j:
            reclamados.append(j["id"])
    assert len(reclamados) == MAX_POR_CUENTA, f"nunca supera {MAX_POR_CUENTA} en running"
    assert len(store._select("jobs", account_id="A", status="running")) <= MAX_POR_CUENTA


async def test_dos_workers_no_toman_el_mismo(app_test, store):
    """Dos reclamos simultáneos sobre una cola de un solo trabajo: uno se lo
    lleva, el otro se va vacío. Nunca los dos."""
    await _encolar("A", "unico", 1)
    assert len(store.tables["jobs"]) == 1

    r1, r2 = await asyncio.gather(jq._claim_next_job(), jq._claim_next_job())
    ganadores = [j for j in (r1, r2) if j]
    assert len(ganadores) == 1, "solo un worker se lleva el trabajo"
    assert len(store._select("jobs", status="running")) == 1


async def test_sin_hueco_el_worker_duerme(app_test, store):
    """Si todas las cuentas están en su tope, reclamar devuelve None (no da vueltas)."""
    await _encolar("A", "A", 5)
    assert len(store.tables["jobs"]) == 5

    for _ in range(MAX_POR_CUENTA):
        assert await jq._claim_next_job() is not None
    # todas las cuentas al tope → sin hueco
    assert await jq._claim_next_job() is None


async def test_pesados_limitados(app_test, monkeypatch):
    """El freno pesado: el semáforo no deja correr más de su valor a la vez.
    KIND_GENERAR_VIDEO está en _KIND_PESADOS (renderiza por Chromium)."""
    assert KIND_GENERAR_VIDEO in jq._KIND_PESADOS, "el vídeo debe pasar por el freno pesado"
    sem = asyncio.Semaphore(2)
    monkeypatch.setattr(jq, "_SEMAFORO_PESADO", sem)

    dentro = 0
    pico = 0

    async def _pesado():
        nonlocal dentro, pico
        async with sem:
            dentro += 1
            pico = max(pico, dentro)
            await asyncio.sleep(0.05)
            dentro -= 1

    await asyncio.gather(*[_pesado() for _ in range(5)])
    assert pico <= 2, f"tres vídeos no corren a la vez (pico {pico})"