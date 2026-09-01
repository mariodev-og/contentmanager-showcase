"""
Aislamiento entre cuentas (ETAPA 0.3).

La prueba que caza el hallazgo #1 de la auditoría: una comprobación de cuenta
que existe en una ruta y falta en su gemela. Se escribió ANTES de arreglar nada:
debe verse fallar hoy en las 15 rutas conocidas (listadas con el número de línea
de `app/panel/routes.py` en el parametrize).

NO se marcan `xfail`: tienen que estar en rojo, a la vista, hasta que la ETAPA
1.1 las arregle. En ese momento estas pruebas pasan solas.

Escenarios de normas.md 7.2: ajena_lectura, ajena_escritura, ajena_en_lista,
id_inventado.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from tests.conftest import ALFA, BETA
from tests.factories import pieza

pytestmark = pytest.mark.aislamiento

MARKER = "BETA-SECRETO"

# (linea_routes.py, metodo, path, estado_pieza_beta, form_minimo)
RUTAS = [
    (1921, "POST", "/panel/piezas/{piece_id}/seleccionar", "generado", {"accion": "1"}),
    (1930, "POST", "/panel/piezas/{piece_id}/archivar", "generado", {"accion": "1"}),
    (2001, "POST", "/panel/piezas/{piece_id}/agendar", "generado", {"when": "2030-01-01T10:00:00Z", "accion": "1"}),
    (2392, "GET",  "/panel/piezas/{piece_id}/export", "generado", None),
    (2450, "GET",  "/panel/api/piezas/{piece_id}/preview", "generado", None),
    (2548, "GET",  "/panel/piezas/{piece_id}/editar", "generado", None),
    (2586, "POST", "/panel/piezas/{piece_id}/editar", "generado", {"title": "x", "body": "y", "accion": "1"}),
    (2662, "POST", "/panel/piezas/{piece_id}/slide/{slide_id}/editar-imagen", "generado", {"edit_prompt": "mejorar luz", "accion": "1"}),
    (2695, "POST", "/panel/piezas/{piece_id}/slide/{slide_id}/regenerar", "generado", {"accion": "1"}),
    (2817, "POST", "/panel/cronograma/{piece_id}/cancelar", "agendado", {"accion": "1"}),
    (2833, "POST", "/panel/cronograma/{piece_id}/pausar", "agendado", {"accion": "1"}),
    (2852, "POST", "/panel/cronograma/{piece_id}/reanudar", "agendado", {"accion": "1"}),
    (2871, "POST", "/panel/cronograma/{piece_id}/modificar", "agendado", {"when": "2030-02-01T10:00:00Z", "accion": "1"}),
    (3025, "POST", "/panel/piezas/{piece_id}/slide/{slide_id}/guardar", "generado", {"accion": "1"}),
    (3140, "POST", "/panel/piezas/{piece_id}/agregar-imagen", "generado", {"modo": "generar", "title": "t", "body": "b", "prompt": "foto de frente", "accion": "1"}),
]

RUTAS_LECTURA = [(ln, m, p, e, f) for (ln, m, p, e, f) in RUTAS if m == "GET"]
RUTAS_ESCRITURA = [(ln, m, p, e, f) for (ln, m, p, e, f) in RUTAS if m == "POST"]


def _beta_pieza(store, estado: str, suffix: str = "a") -> dict:
    return pieza(store, BETA, status=estado, brief=f"{MARKER} {suffix}",
                 caption=f"{MARKER} {suffix}", kind="carrusel")


def _url(path: str, piece_id: str, slide_id: str) -> str:
    return path.replace("{piece_id}", piece_id).replace("{slide_id}", slide_id)


def _texto_resp(resp) -> str:
    """Texto del body. Si es un ZIP (export), extrae los archivos internos:
    el contenido útil va comprimido y no aparece como texto plano."""
    body = resp.content
    if body[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                return "\n".join(
                    z.read(n).decode("utf-8", errors="ignore") for n in z.namelist()
                )
        except zipfile.BadZipFile:
            pass
    return body.decode("latin-1", errors="ignore")


@pytest.mark.parametrize("linea,metodo,path,estado,form", RUTAS_LECTURA)
async def test_ajena_lectura(linea, metodo, path, estado, form, como, store):
    """Alfa pide por URL el recurso de beta: NO lo recibe."""
    beta = _beta_pieza(store, estado)
    slide = store._first("slides", piece_id=beta["id"])
    url = _url(path, beta["id"], slide["id"])
    client = await como("client", ALFA)
    resp = await client.get(url)
    body = _texto_resp(resp)
    assert not (resp.status_code == 200 and MARKER in body), (
        f"LEAK {path} (linea {linea}): alfa recibio contenido de beta "
        f"(HTTP {resp.status_code})"
    )


@pytest.mark.parametrize("linea,metodo,path,estado,form", RUTAS_ESCRITURA)
async def test_ajena_escritura(linea, metodo, path, estado, form, como, store):
    """Alfa manda formulario contra el recurso de beta. Se comprueba contra el
    store, no contra el código de respuesta: el dato de beta NO cambió, y no
    queda trabajo (jobs/biblioteca) referenciando piezas ni slides de beta."""
    beta = _beta_pieza(store, estado)
    slide = store._first("slides", piece_id=beta["id"])
    url = _url(path, beta["id"], slide["id"])

    p_before = dict(store._first("pieces", id=beta["id"]))
    slides_before = [dict(s) for s in store._select("slides", piece_id=beta["id"])]
    njobs_before = len(store.tables["jobs"])
    nlib_before = len(store.tables["saved_images"])
    ids_slides_before = {s["id"] for s in slides_before}

    client = await como("client", ALFA)
    await client.post(url, data=form)

    p_after = store._first("pieces", id=beta["id"])
    assert p_after == p_before, (
        f"LEAK {path} (linea {linea}): alfa modifico la pieza de beta "
        f"({p_after.get('status')})"
    )
    slides_after = [dict(s) for s in store._select("slides", piece_id=beta["id"])]
    assert slides_after == slides_before, (
        f"LEAK {path} (linea {linea}): alfa modifico slides de beta"
    )

    jobs_nuevos = store.tables["jobs"][njobs_before:]
    for j in jobs_nuevos:
        payload = j.get("payload") or {}
        assert payload.get("piece_id") != beta["id"], (
            f"LEAK {path} (linea {linea}): alfa encolo trabajo sobre la pieza de beta"
        )
        assert payload.get("slide_id") not in ids_slides_before, (
            f"LEAK {path} (linea {linea}): alfa encolo trabajo sobre un slide de beta"
        )

    lib_nueva = store.tables["saved_images"][nlib_before:]
    assert not any(s.get("source_piece_id") == beta["id"] for s in lib_nueva), (
        f"LEAK {path} (linea {linea}): alfa copio la imagen de beta a su biblioteca"
    )


async def test_ajena_en_lista(como, store):
    """Ningun listado de alfa contiene identificadores de beta."""
    beta_pieces = [r["id"] for r in store._select("pieces", account_id=BETA)]
    beta_props = [r["id"] for r in store._select("properties", account_id=BETA)]
    client = await como("client", ALFA)
    for url in ("/panel/piezas", "/panel/cronograma", "/panel/propiedades"):
        resp = await client.get(url)
        body = resp.content.decode("utf-8", errors="ignore")
        for bid in beta_pieces:
            assert bid not in body, f"LEAK en lista {url}: pieza de beta {bid}"
        for bid in beta_props:
            assert bid not in body, f"LEAK en lista {url}: propiedad de beta {bid}"


@pytest.mark.parametrize("linea,metodo,path,estado,form", RUTAS)
async def test_id_inventado(linea, metodo, path, estado, form, como):
    """Un UUID que no existe: redireccion o 404, nunca 500."""
    fake = "00000000-0000-0000-0000-000000000000"
    url = _url(path, fake, fake)
    client = await como("client", ALFA)
    if metodo == "POST":
        resp = await client.post(url, data=form or {"accion": "1"})
    else:
        resp = await client.get(url)
    assert resp.status_code < 500, f"{path} (linea {linea}) -> HTTP {resp.status_code}"