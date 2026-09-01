# ContentManager

> SaaS multi-inmobiliaria: cada agencia gestiona sus propiedades y genera contenido para redes, con aprobación humana antes de publicar.

**Este repositorio es una vitrina técnica, no el sistema.** El sistema en
producción es privado. Acá están la arquitectura, las decisiones de diseño, las
pruebas y algunos fragmentos de código elegidos para mostrar cómo está resuelto.

---

## El problema

Una inmobiliaria publica decenas de propiedades por mes en redes, y cada pieza
—precio, superficie, ambientes, zona— tiene que ser exacta: un dato mal puesto
es información comercial falsa a nombre de la agencia. Las herramientas de
generación con IA producen texto lindo pero alucinan datos duros, y ninguna
resuelve que varias agencias trabajen sobre el mismo sistema sin verse entre sí.

ContentManager es un panel multi-cuenta donde cada agencia carga sus propiedades,
genera piezas para redes (post, carrusel, historia), arma un cronograma editorial
y aprueba antes de publicar. La regla que atraviesa todo: los datos duros los
pone el sistema desde la base, nunca el modelo.

## Arquitectura

```
Panel /admin (Jinja2 + HTMX + Tailwind, gráficos con Chart.js)
      │  cada request lleva account_id — aislamiento por cuenta
      ▼
Propiedades ──► Cola de trabajos async (reparto justo entre cuentas)
      │                    │
      │                    ▼
      │           Generación: LLM escribe el copy · template dibuja la ficha
      │                    │      (Claude / Gemini, routing por tarea)
      ▼                    ▼
Cronograma editorial ──► Aprobación humana ──► Publicación
```

Detalle en [`docs/arquitectura.md`](docs/arquitectura.md).

## Stack

| Capa | Tecnología | Por qué esta y no otra |
|---|---|---|
| Backend | Python · FastAPI | Async para la cola y los webhooks, un solo lenguaje |
| Base de datos | PostgreSQL sobre Supabase | Multi-tenant con Storage incluido |
| Interfaz | Jinja2 · HTMX · Tailwind · Chart.js | Panel reactivo sin construir una SPA |
| IA | Claude · Gemini | Routing de modelo por tarea, con costo medido |
| Imagen | Pillow · Chromium headless | Ficha determinística y slides HTML/CSS |
| Video | Remotion (React/TS) | Render de reels con plantilla |
| Despliegue | Docker · Railway | Imagen reproducible, deploy por rama |

## Decisiones de diseño

Detalle completo en [`docs/decisiones.md`](docs/decisiones.md).

### Ficha técnica determinística

- **Qué se hizo:** los datos duros de la propiedad se dibujan por template desde la base; el LLM no los escribe nunca.
- **Alternativa descartada:** pedirle al modelo que redacte la ficha completa.
- **Por qué:** una alucinación en precio, superficie o zona es información comercial y legal falsa publicada a nombre de la inmobiliaria.
- **Qué costó:** las fichas son más rígidas y menos "naturales" que un texto libre.

### La cola reparte por cuenta, no por orden de llegada

- **Qué se hizo:** round-robin con tope de workers por cuenta (`MAX_POR_CUENTA`).
- **Alternativa descartada:** FIFO — el más viejo primero.
- **Por qué:** una agencia que encolaba 40 piezas dejaba a las demás sin servicio.
- **Qué costó:** más estado que mantener y una cola más difícil de razonar; ver el bug de `count()` documentado en el snippet.

### Nada publica ni gasta sin confirmación humana

- **Qué se hizo:** toda pieza pasa por un estado de aprobación registrado antes de publicarse o gastar tokens.
- **Alternativa descartada:** un modo totalmente automático.
- **Qué costó:** hay un humano en el camino crítico; el sistema no escala solo.

## Decisiones sobre este repositorio

- **Es una vitrina, no un espejo.** El sistema en producción tiene material de clientes: nombres de agencias, propiedades reales, cuentas de Instagram. Publicarlo entero no era una opción.
- **Se publica lo que se lee, no lo que pesa.** `app/panel/routes.py` tiene 4288 líneas; no aporta a quien evalúa en cinco minutos. En su lugar van fragmentos elegidos, uno por decisión.
- **Los tests sí van completos.** Cuatro de las 18 suites reales, las que mejor muestran el criterio: aislamiento entre cuentas, cola justa, costos y cuotas.
- **Los nombres de cliente están reemplazados** por ficticios (`cliente_demo`), no ofuscados.

## Qué hay en este repositorio

| Carpeta | Qué contiene |
|---|---|
| [`docs/`](docs/) | Arquitectura, decisiones y capturas |
| [`snippets/`](snippets/) | Cuatro fragmentos comentados, uno por decisión |
| [`tests/`](tests/) | Cuatro de las 18 suites reales del proyecto |

Los fragmentos de `snippets/` no forman un programa ejecutable: están para leerse.

## Escala del proyecto

137 commits · 61 módulos Python · 43 vistas · 18 suites de test · multi-tenant
con aislamiento por cuenta. En desarrollo activo desde julio de 2026.

## Estado

En desarrollo activo. Repositorio de producción privado.

---

## Código completo

El repositorio de producción es privado porque contiene material de clientes.
Puedo dar acceso de lectura durante un proceso de selección: escribime a
**mario1804.dev@gmail.com**.

## Licencia

Todos los derechos reservados. Ver [`LICENSE`](LICENSE).
