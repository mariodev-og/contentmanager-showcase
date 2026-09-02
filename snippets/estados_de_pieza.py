# Español primero · English below
# Origen: app/piece.py del sistema en produccion (fragmento: estados,
# can_transition y la clase Piece; se recorto caption_de_publicacion).
# Ilustra: cada pieza es una maquina de estados explicita. El paso a
# 'agendado' exige confirmed_by y confirmed_at — nada se publica ni se
# programa sin una aprobacion humana registrada en la base.
#
# --- English ---
# Source: app/piece.py from the production system (fragment: statuses,
# can_transition and the Piece class; caption_de_publicacion was trimmed).
# Shows: every content piece is an explicit state machine. Moving to 'scheduled'
# requires confirmed_by and confirmed_at — nothing publishes or schedules without
# a human approval recorded in the database.

"""
Pieza generada por ContentManager (carrusel, historia, post).

State machine:
    generado -> seleccionado -> borrador -> agendado -> publicado
                                                     -> archivado
                                                     -> fallido

Reglas:
    - generado    : salida cruda del pipeline, no ha pasado por el jefe.
    - seleccionado: el jefe lo eligio de entre las opciones de la tanda.
    - borrador    : el jefe pidio editar algo.
    - agendado    : requiere scheduled_at + confirmed_by + confirmed_at.
    - publicado   : requiere ig_media_id + published_at. Estado terminal.
    - archivado   : carruseles no elegidos — reutilizables, NO se borran.
    - fallido     : error irrecuperable; se puede reintentar (-> generado).

Dataclass espejo de la tabla pieces en Supabase (supabase/schema.sql).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class PieceStatus(str, Enum):
    GENERADO    = "generado"
    SELECCIONADO = "seleccionado"
    BORRADOR    = "borrador"
    AGENDADO    = "agendado"
    # 1.5c: el octavo estado. La DB ya lo conoce (migration_paused_status.sql,
    # verificado contra producción el 21/08); faltaba declararlo en la
    # enumeración. Transiciones documentadas en VALID_TRANSITIONS.
    PAUSADO     = "pausado"
    PUBLICADO   = "publicado"
    ARCHIVADO   = "archivado"
    FALLIDO     = "fallido"


class PieceKind(str, Enum):
    CARRUSEL = "carrusel"
    HISTORIA = "historia"
    POST     = "post"


class FunnelStage(str, Enum):
    TOFU     = "tofu"
    MOFU     = "mofu"
    BOFU     = "bofu"
    GENERICO = "generico"


VALID_TRANSITIONS: dict[PieceStatus, set[PieceStatus]] = {
    PieceStatus.GENERADO:     {PieceStatus.SELECCIONADO, PieceStatus.ARCHIVADO, PieceStatus.FALLIDO},
    PieceStatus.SELECCIONADO: {PieceStatus.BORRADOR, PieceStatus.AGENDADO, PieceStatus.PUBLICADO, PieceStatus.ARCHIVADO},
    PieceStatus.BORRADOR:     {PieceStatus.SELECCIONADO, PieceStatus.AGENDADO, PieceStatus.PUBLICADO, PieceStatus.ARCHIVADO},
    PieceStatus.AGENDADO:     {PieceStatus.PUBLICADO, PieceStatus.BORRADOR, PieceStatus.ARCHIVADO, PieceStatus.FALLIDO, PieceStatus.PAUSADO},
    # 1.5c: pausado se escribe/lee en el cronograma; se reanuda (agendado),
    # se cancela (seleccionado) o se edita (borrador).
    PieceStatus.PAUSADO:      {PieceStatus.AGENDADO, PieceStatus.BORRADOR, PieceStatus.ARCHIVADO, PieceStatus.FALLIDO, PieceStatus.SELECCIONADO},
    PieceStatus.PUBLICADO:    set(),
    PieceStatus.ARCHIVADO:    {PieceStatus.SELECCIONADO},
    PieceStatus.FALLIDO:      {PieceStatus.GENERADO},
}


def can_transition(from_status: PieceStatus, to_status: PieceStatus) -> bool:
    return to_status in VALID_TRANSITIONS.get(from_status, set())


@dataclass
class Slide:
    position: int
    title: str | None = None
    title_en: str | None = None
    body: str | None = None
    body_en: str | None = None
    image_prompt: str | None = None
    image_url: str | None = None
    image_base_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Piece:
    id: UUID = field(default_factory=uuid4)
    account_id: str = ""
    kind: PieceKind = PieceKind.CARRUSEL
    status: PieceStatus = PieceStatus.GENERADO

    brief: str | None = None
    funnel_stage: FunnelStage = FunnelStage.GENERICO
    caption: str | None = None
    caption_en: str | None = None
    hashtags: list[str] = field(default_factory=list)
    slides: list[Slide] = field(default_factory=list)

    confirmed_by: str | None = None
    confirmed_at: datetime | None = None

    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    ig_media_id: str | None = None
    ig_permalink: str | None = None

    property_id: str | None = None

    idempotency_key: str | None = None
    generation_log: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def transition(self, to: PieceStatus) -> None:
        if not can_transition(self.status, to):
            raise ValueError(f"transicion invalida: {self.status} -> {to}")
        self.status = to
        self.updated_at = datetime.utcnow()

    @property
    def is_publishable(self) -> bool:
        return (
            self.confirmed_by is not None
            and self.confirmed_at is not None
            and self.status in (PieceStatus.AGENDADO, PieceStatus.SELECCIONADO, PieceStatus.BORRADOR)
            and bool(self.slides)
        )
