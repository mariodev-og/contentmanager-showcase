**🇦🇷 Español · 🇬🇧 [English](#-english)**

# Decisiones de diseño

Cada decisión con sus cuatro partes: qué se hizo, contra qué, por qué, y qué costó.

## 1. Ficha técnica determinística

- **Qué se hizo:** precio, superficie, ambientes y zona se dibujan por template
  con Pillow, tomados de la base. El LLM escribe el copy alrededor, nunca el dato.
- **Alternativa descartada:** pedirle al modelo que redacte la ficha entera.
- **Por qué:** una alucinación en un dato duro es información comercial y legal
  falsa publicada a nombre de la inmobiliaria. El copy puede ser creativo; el
  precio no puede estar mal.
- **Qué costó:** las fichas son más rígidas. Se resignó naturalidad a cambio de
  que ningún número publicado pueda ser inventado.

## 2. La cola reparte por cuenta, no por orden de llegada

- **Qué se hizo:** round-robin con un tope de workers en running por cuenta.
- **Alternativa descartada:** FIFO, el trabajo más viejo primero.
- **Por qué:** con FIFO, una agencia que encolaba 40 piezas dejaba a las demás
  esperando horas. El reparto justo garantiza avance para todas.
- **Qué costó:** más estado y una cola más difícil de razonar. El snippet
  documenta un bug real que salió de esta complejidad: PostgREST traía los
  agregados deshabilitados y la cola dejó de reclamar trabajos en producción,
  y la suite no lo vio porque el doble sí los implementaba.

## 3. Recuperación ante caída sin cobro duplicado

- **Qué se hizo:** un trabajo interrumpido vuelve a 'queued' y se puede reclamar
  de nuevo sin volver a pagarle al proveedor de LLM.
- **Por qué:** un proceso que cae a mitad de una generación no puede dejar el
  trabajo colgado ni cobrar dos veces la misma pieza.
- **Qué costó:** obligó a hacer idempotente el registro de consumo.

## 4. Nada publica ni gasta sin confirmación humana

- **Qué se hizo:** toda pieza pasa por un estado de aprobación registrado antes
  de publicarse o gastar tokens.
- **Alternativa descartada:** un modo automático de punta a punta.
- **Por qué:** el sistema opera sobre las cuentas reales de las agencias; una
  publicación equivocada es cara de revertir.
- **Qué costó:** hay un humano en el camino crítico. El sistema no escala solo.

---

<a name="english"></a>
# 🇬🇧 English — Design decisions

Each decision with four parts: what was done, against what, why, and what it cost.

## 1. Deterministic spec sheet

- **What:** price, area, rooms and location are drawn by template with Pillow,
  taken from the database. The LLM writes the surrounding copy, never the data.
- **Rejected alternative:** ask the model to write the whole spec sheet.
- **Why:** a hallucination in hard data is false commercial and legal
  information under the agency's name. Copy can be creative; the price can't be wrong.
- **Cost:** spec sheets are more rigid. Naturalness was traded so no published
  number can be invented.

## 2. The queue dispatches per account, not first-come-first-served

- **What:** round-robin with a per-account cap on running workers.
- **Rejected alternative:** FIFO, oldest job first.
- **Why:** with FIFO, an agency enqueuing 40 pieces left the others waiting
  hours. Fair dispatch guarantees progress for all.
- **Cost:** more state and a harder queue to reason about. The snippet documents
  a real bug this complexity produced: PostgREST shipped aggregates disabled and
  the queue stopped claiming jobs in production, and the suite missed it because
  the test double did implement them.

## 3. Crash recovery without double charging

- **What:** an interrupted job returns to 'queued' and can be reclaimed without
  paying the LLM provider again.
- **Why:** a process that dies mid-generation can't leave the job stuck or charge
  the same piece twice.
- **Cost:** it forced the consumption record to be idempotent.

## 4. Nothing publishes or spends without human approval

- **What:** every piece goes through a recorded approval state before publishing
  or spending tokens.
- **Rejected alternative:** a fully automatic end-to-end mode.
- **Why:** the system operates on the agencies' real accounts; a wrong
  publication is expensive to undo.
- **Cost:** there's a human on the critical path. The system doesn't scale alone.
