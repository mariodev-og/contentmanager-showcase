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
