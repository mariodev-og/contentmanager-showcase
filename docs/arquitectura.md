# Arquitectura

## Flujo de datos

```
1. La agencia entra al panel /admin. Cada request lleva su account_id;
   el aislamiento por cuenta se verifica en cada handler.

2. Carga una propiedad (precio, superficie, ambientes, zona, fotos).
   Los datos duros quedan en la base, normalizados.

3. Pide generar una pieza. El trabajo NO se ejecuta en el request:
   se encola. La cola reparte por cuenta (round-robin), no por orden
   de llegada, para que una agencia no monopolice los workers.

4. El worker toma el trabajo:
   - el LLM (Claude o Gemini, según la tarea) escribe el copy;
   - la ficha técnica se dibuja por template con Pillow, tomando los
     datos duros de la base — el modelo no los toca;
   - los slides de carrusel se renderizan como HTML/CSS con Chromium
     headless, con fallback a Pillow.

5. La pieza queda en estado 'pendiente de aprobación'. Nada se publica
   ni gasta tokens de más sin que un humano la confirme (registrado).

6. Aprobada, entra al cronograma editorial de esa cuenta.
```

## Multi-tenancy

El `account_id` atraviesa todo el sistema: selecciona configuración, aísla los
datos y enruta la cola. La validación de que una cuenta no vea las propiedades
ni las piezas de otra es una preocupación de primer orden — de ahí la suite de
aislamiento en `tests/`.

## Control de costo

Cada llamada al LLM estima su costo por tokens de entrada y salida (ver
`snippets/routing_de_modelo.py`). Sobre esa medición se apoyan el presupuesto
tope por cuenta y el corte de gasto.
