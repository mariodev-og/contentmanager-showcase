# Español primero · English below
# Origen: app/job_queue.py del sistema en produccion (fragmento: _claim_next_job).
# Ilustra: la cola no reparte por orden de llegada sino por cuenta — ninguna
# ocupa mas de MAX_POR_CUENTA workers a la vez, para que una inmobiliaria que
# encola 40 piezas no deje a las demas sin servicio. El comentario del count()
# es un bug real de produccion: PostgREST traia los agregados deshabilitados y
# la cola dejo de reclamar trabajos; la suite no lo vio porque el doble si los
# implementaba. Se cuenta en Python, que aca es barato (running acotado por WORKERS).
#
# --- English ---
# Source: app/job_queue.py from the production system (fragment: _claim_next_job).
# Shows: the queue does not dispatch first-come-first-served but per account — none
# takes more than MAX_POR_CUENTA workers at once, so an agency that enqueues 40
# pieces can't starve the others. The count() comment is a real production bug:
# PostgREST shipped aggregates disabled and the queue stopped claiming jobs; the
# suite missed it because the test double did implement them. Counting in Python is
# cheap here (running rows bounded by WORKERS).

async def _claim_next_job() -> dict | None:
    """Toma el trabajo más viejo de una cuenta que todavía tenga hueco.

    ETAPA 3.5.2 (reparto justo): ya no es "el más viejo de todos", es "el más
    viejo de una cuenta que no haya alcanzado MAX_POR_CUENTA en running".
    Algoritmo en el orden del plan:
      1. cuentas_ocupadas: las que ya alcanzaron MAX_POR_CUENTA (una consulta
         agrupada con count()).
      2. el más viejo en queued de una cuenta que NO esté ocupada (priority+fecha).
      3. marcarlo running con la condición que ya existe — con N workers dos
         pueden elegir el mismo y solo uno gana; el que pierde reintenta.
      4. revalidar el tope tras ganar: si la cuenta quedó por encima, devolver
         el trabajo a queued y seguir (dos workers pueden colarse a la vez).
    """
    from app.supabase_client import get_supabase, _run
    try:
        sb = get_supabase()

        # 1. cuentas que ya alcanzaron el tope en running.
        #
        # NO se usa el agregado `count()` de PostgREST: Supabase lo trae
        # DESHABILITADO por defecto y devuelve PGRST123 "Use of aggregate
        # functions is not allowed". Eso dejó la cola sin poder reclamar ni un
        # trabajo en producción, y la suite no lo vio porque el doble sí
        # implementaba el agregado.
        #
        # Contar en Python aquí es barato de verdad: los `running` están
        # acotados por WORKERS (10), así que son unas pocas filas, no una tabla.
        def _ocupadas():
            return (
                sb.table("jobs").select("account_id")
                .eq("status", "running")
                .execute()
            )

        res = await _run(_ocupadas)
        conteo: dict[str, int] = {}
        for r in (res.data or []):
            aid = r.get("account_id")
            if aid:
                conteo[aid] = conteo.get(aid, 0) + 1
        ocupadas = {aid for aid, n in conteo.items() if n >= MAX_POR_CUENTA}

        # 2. el más viejo en queued de una cuenta con hueco.
        def _q():
            q = sb.table("jobs").select("*").eq("status", "queued")
            if ocupadas:
                q = q.not_.in_("account_id", sorted(ocupadas))
            return q.order("priority").order("created_at", desc=False).limit(1).execute()

        res = await _run(_q)
        if not res.data:
            return None
        job = res.data[0]

        # 3. marcarlo running: solo si sigue queued (race con otros workers).
        def _u():
