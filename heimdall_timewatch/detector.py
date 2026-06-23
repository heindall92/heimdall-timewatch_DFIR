"""
heimdall-timewatch :: detector.py
═══════════════════════════════════════════════════════════════════════════

Motor de detección de timestomping. Aplica varias heurísticas independientes
sobre los registros parseados y asigna a cada archivo una puntuación de
sospecha y una lista de hallazgos.

FILOSOFÍA HONESTA (esto importa mucho en DFIR):
  Ninguna heurística es prueba concluyente por sí sola. Este motor NO grita
  "¡timestomping!" — acumula INDICADORES y deja que el analista decida. Cada
  hallazgo lleva su nivel de confianza y una nota sobre sus falsos positivos
  conocidos. Un buen detector que miente sobre su certeza es peor que ninguno.

Heurísticas implementadas:
  H1  $SI anterior a $FN          (el método clásico; confianza MEDIA)
  H2  Subsegundos en cero         (precisión redondeada; confianza BAJA)
  H3  Desorden de RID vs creación (entry number vs birth; confianza BAJA)
  H4  $SI created > $SI modified  (imposible lógico; confianza MEDIA)
  H5  Timestamps fuera de rango    (futuro / pre-instalación; confianza MEDIA)
  H6  $FN nanosegundos en cero     (el kernel no redondea; confianza MEDIA)

Autor: Yoandy Ramirez Delgado  |  Uso educativo / DFIR autorizado
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from .mft_parser import MftRecord, filetime_subsecond_100ns


# ───────────────────────────────────────────────────────────────────────────
# Niveles de confianza y modelo de hallazgo
# ───────────────────────────────────────────────────────────────────────────

class Confidence:
    HIGH = "ALTA"
    MEDIUM = "MEDIA"
    LOW = "BAJA"


# Peso de cada nivel para la puntuación agregada
CONFIDENCE_WEIGHT = {
    Confidence.HIGH: 50,
    Confidence.MEDIUM: 25,
    Confidence.LOW: 10,
}


@dataclass
class Finding:
    """Un indicador concreto detectado sobre un archivo."""
    code: str               # p.ej. "H1"
    title: str              # descripción corta
    confidence: str         # Confidence.*
    detail: str             # explicación del caso concreto
    false_positive_note: str  # cuándo este indicador miente


@dataclass
class FileVerdict:
    """El veredicto agregado sobre un archivo."""
    record_number: int
    filename: Optional[str]
    is_directory: bool
    in_use: bool
    findings: list = field(default_factory=list)
    score: int = 0
    filename_namespace: Optional[str] = None
    parent_ref: Optional[int] = None
    si_created: Optional[str] = None
    si_modified: Optional[str] = None
    si_mft_modified: Optional[str] = None
    si_accessed: Optional[str] = None
    fn_created: Optional[str] = None
    fn_modified: Optional[str] = None
    fn_mft_modified: Optional[str] = None
    fn_accessed: Optional[str] = None

    @property
    def suspicion_level(self) -> str:
        if self.score >= 70:
            return "CRÍTICO"
        if self.score >= 45:
            return "ALTO"
        if self.score >= 20:
            return "MEDIO"
        if self.score > 0:
            return "BAJO"
        return "LIMPIO"

    def add(self, finding: Finding):
        self.findings.append(finding)
        self.score += CONFIDENCE_WEIGHT.get(finding.confidence, 0)


def _iso_dt(value: Optional[datetime.datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.isoformat()


def _snapshot_timestamps(rec: MftRecord) -> dict[str, Optional[str]]:
    si = rec.si_timestamps
    fn = rec.fn_timestamps
    return {
        "filename_namespace": rec.filename_namespace,
        "parent_ref": rec.parent_ref,
        "si_created": _iso_dt(si.created) if si else None,
        "si_modified": _iso_dt(si.modified) if si else None,
        "si_mft_modified": _iso_dt(si.mft_modified) if si else None,
        "si_accessed": _iso_dt(si.accessed) if si else None,
        "fn_created": _iso_dt(fn.created) if fn else None,
        "fn_modified": _iso_dt(fn.modified) if fn else None,
        "fn_mft_modified": _iso_dt(fn.mft_modified) if fn else None,
        "fn_accessed": _iso_dt(fn.accessed) if fn else None,
    }


# ───────────────────────────────────────────────────────────────────────────
# Heurísticas individuales
# ───────────────────────────────────────────────────────────────────────────

def h1_si_before_fn(rec: MftRecord) -> Optional[Finding]:
    """
    H1 — El método clásico. Si los timestamps de $SI (modificables en
    user-mode) son ANTERIORES a los de $FN (solo escribe el kernel), el
    archivo probablemente fue retrocedido en el tiempo (timestomping).

    LÍMITE HONESTO: si el atacante renombró o movió el archivo en el mismo
    volumen DESPUÉS de timestompear, Windows copia el $SI manipulado al $FN
    y la discrepancia desaparece. Además, algunos instaladores legítimos
    tocan el $SI. Por eso la confianza es MEDIA, no ALTA.
    """
    if not (rec.si_timestamps and rec.fn_timestamps):
        return None

    si = rec.si_timestamps
    fn = rec.fn_timestamps

    # Comparamos created y modified (los más usados en timestomping)
    suspicious_pairs = []
    max_delta_seconds = 0
    if si.created and fn.created and si.created < fn.created:
        delta = fn.created - si.created
        if delta.total_seconds() > 1:  # margen para evitar ruido de ms
            suspicious_pairs.append(
                f"$SI.created ({si.created}) < $FN.created ({fn.created}), "
                f"diferencia {delta}"
            )
            max_delta_seconds = max(max_delta_seconds, delta.total_seconds())
    if si.modified and fn.modified and si.modified < fn.modified:
        delta = fn.modified - si.modified
        if delta.total_seconds() > 1:
            suspicious_pairs.append(
                f"$SI.modified ({si.modified}) < $FN.modified ({fn.modified}), "
                f"diferencia {delta}"
            )
            max_delta_seconds = max(max_delta_seconds, delta.total_seconds())

    if not suspicious_pairs:
        return None

    # La MAGNITUD del retroceso modula la confianza. Un desfase de minutos
    # puede ser ruido legítimo; un retroceso de meses o años es muy difícil
    # de explicar sin manipulación deliberada.
    THIRTY_DAYS = 30 * 24 * 3600
    if max_delta_seconds >= THIRTY_DAYS:
        conf = Confidence.HIGH
        magnitude = "retroceso masivo (>30 días): muy improbable sin manipulación"
    else:
        conf = Confidence.MEDIUM
        magnitude = "retroceso moderado: requiere corroboración"

    return Finding(
        code="H1",
        title=f"$SI anterior a $FN — {magnitude}",
        confidence=conf,
        detail="; ".join(suspicious_pairs),
        false_positive_note=(
            "Si el archivo se renombró/movió en el mismo volumen tras "
            "timestompear, $SI se copia a $FN y este indicador NO dispara "
            "(falso negativo). Algunos instaladores modifican $SI "
            "legítimamente (falso positivo)."
        ),
    )


def h2_zero_subseconds_si(rec: MftRecord) -> Optional[Finding]:
    """
    H2 — Muchas herramientas de timestomping solo permiten precisión al
    segundo, dejando los subsegundos en .0000000. El SO normalmente genera
    timestamps con subsegundos no nulos.

    LÍMITE HONESTO: algunos formatos (archivos comprimidos, ciertos
    instaladores) truncan al segundo de forma legítima. Confianza BAJA.
    """
    if not rec.si_timestamps:
        return None

    si = rec.si_timestamps
    zero_fields = []
    for name, dt, raw in si.as_list():
        if dt is not None and filetime_subsecond_100ns(raw) == 0:
            zero_fields.append(name)

    # Solo es interesante si VARIOS campos están redondeados a la vez
    if len(zero_fields) >= 3:
        return Finding(
            code="H2",
            title="Subsegundos de $SI en cero (precisión redondeada)",
            confidence=Confidence.LOW,
            detail=f"Campos con .0000000: {', '.join(zero_fields)}",
            false_positive_note=(
                "Archivos extraídos de ZIP/archivos comprimidos y algunos "
                "instaladores truncan subsegundos legítimamente. No "
                "concluyente por sí solo."
            ),
        )
    return None


def h4_created_after_modified(rec: MftRecord) -> Optional[Finding]:
    """
    H4 — Imposibilidad lógica: un archivo no puede haber sido MODIFICADO
    antes de ser CREADO. Si $SI.created > $SI.modified por un margen
    significativo, alguien manipuló los timestamps de forma descuidada.

    LÍMITE HONESTO: ciertas operaciones de copia y algunos sistemas de
    backup pueden producir esto legítimamente (al restaurar mtime original
    sobre un archivo recién creado). Confianza MEDIA.
    """
    if not rec.si_timestamps:
        return None
    si = rec.si_timestamps
    if si.created and si.modified and si.created > si.modified:
        delta = si.created - si.modified
        # Margen amplio: copias legítimas pueden dar segundos de diferencia
        if delta.total_seconds() > 60:
            return Finding(
                code="H4",
                title="$SI.created posterior a $SI.modified (imposible lógico)",
                confidence=Confidence.MEDIUM,
                detail=(
                    f"created ({si.created}) > modified ({si.modified}), "
                    f"diferencia {delta}"
                ),
                false_positive_note=(
                    "Copias de archivos y restauraciones de backup que "
                    "preservan el mtime original sobre un archivo nuevo "
                    "pueden producir esto de forma legítima."
                ),
            )
    return None


def h5_out_of_range(rec: MftRecord,
                    system_install: Optional[datetime.datetime],
                    now: Optional[datetime.datetime]) -> Optional[Finding]:
    """
    H5 — Timestamps imposibles por contexto:
       · Fechas en el FUTURO respecto al momento del análisis.
       · Fechas ANTERIORES a la instalación del sistema (si se proporciona).

    LÍMITE HONESTO: relojes mal configurados, zonas horarias y archivos
    copiados de sistemas más antiguos pueden disparar esto. Confianza MEDIA.
    """
    if not rec.si_timestamps:
        return None
    si = rec.si_timestamps
    if now is None:
        now = datetime.datetime.now(tz=datetime.timezone.utc)

    issues = []
    for name, dt, _ in si.as_list():
        if dt is None:
            continue
        # Futuro (con 24h de margen para desfases de reloj)
        if dt > now + datetime.timedelta(days=1):
            issues.append(f"{name} en el futuro ({dt})")
        # Anterior a la instalación del sistema
        if system_install and dt < system_install:
            issues.append(
                f"{name} anterior a la instalación del SO "
                f"({dt} < {system_install})"
            )

    if issues:
        return Finding(
            code="H5",
            title="Timestamp fuera de rango (futuro o pre-instalación)",
            confidence=Confidence.MEDIUM,
            detail="; ".join(issues),
            false_positive_note=(
                "Reloj del sistema mal configurado, errores de zona horaria, "
                "o archivos copiados desde un sistema más antiguo pueden "
                "explicar fechas 'imposibles'."
            ),
        )
    return None


def h6_fn_zero_nanoseconds(rec: MftRecord) -> Optional[Finding]:
    """
    H6 — El kernel de Windows, al escribir $FN, no redondea a segundos. Si los
    timestamps de $FN tienen subsegundos exactamente en cero, es inusual y
    puede indicar manipulación avanzada que tocó también el $FN (p.ej. SetMACE
    en sistemas sin PatchGuard), o que el archivo se creó por una vía atípica.

    LÍMITE HONESTO: poco frecuente pero posible en algunos escenarios de
    creación legítima. Confianza MEDIA precisamente porque tocar $FN ya es de
    por sí anómalo.
    """
    if not rec.fn_timestamps:
        return None
    fn = rec.fn_timestamps
    zero_fields = [
        name for name, dt, raw in fn.as_list()
        if dt is not None and filetime_subsecond_100ns(raw) == 0
    ]
    if len(zero_fields) >= 3:
        return Finding(
            code="H6",
            title="Subsegundos de $FN en cero (manipulación avanzada de $FN)",
            confidence=Confidence.MEDIUM,
            detail=f"Campos $FN con .0000000: {', '.join(zero_fields)}",
            false_positive_note=(
                "El $FN normalmente no se redondea. Ver con cautela: ciertas "
                "vías de creación de archivos podrían explicarlo, pero merece "
                "investigación porque tocar $FN no es trivial."
            ),
        )
    return None


# ───────────────────────────────────────────────────────────────────────────
# H3 — Desorden de RID (se evalúa a nivel global, no por registro aislado)
# ───────────────────────────────────────────────────────────────────────────

def h3_rid_birth_disorder(records_with_birth, window_days: int = 7):
    """
    H3 — Los números de registro del MFT (RID) crecen secuencialmente: los
    archivos más antiguos suelen tener RIDs más bajos. Si un archivo tiene un
    RID alto pero una fecha de creación $SI muy anterior a sus vecinos de RID,
    su birth time pudo ser retrocedido.

    Se evalúa comparando cada archivo con la "fecha esperada" según su posición
    en la secuencia de RIDs.

    LÍMITE HONESTO: el MFT reutiliza registros de archivos borrados, así que un
    RID puede contener un archivo nuevo en una posición "vieja". Esto genera
    bastante ruido. Confianza BAJA. Se entrega como pista, no como acusación.

    Args:
        records_with_birth: lista de tuplas (record_number, birth_datetime,
                            filename) ya filtrada (solo archivos con birth).
        window_days: margen de tolerancia.

    Returns:
        dict {record_number: Finding}
    """
    findings = {}
    # Ordenamos por RID
    ordered = sorted(records_with_birth, key=lambda x: x[0])
    if len(ordered) < 10:
        return findings

    # Recorremos con una ventana deslizante calculando la mediana de birth
    # de los vecinos por RID y marcando outliers hacia el pasado.
    import statistics
    window = 25
    for i, (rid, birth, fname) in enumerate(ordered):
        lo = max(0, i - window)
        hi = min(len(ordered), i + window + 1)
        neighbor_births = [
            b.timestamp() for (_, b, _) in ordered[lo:hi]
            if b is not None
        ]
        if len(neighbor_births) < 5:
            continue
        median_ts = statistics.median(neighbor_births)
        median_dt = datetime.datetime.fromtimestamp(
            median_ts, tz=datetime.timezone.utc
        )
        # Si este archivo es MUCHO más antiguo que la mediana de sus vecinos
        if birth < median_dt - datetime.timedelta(days=window_days * 4):
            delta = median_dt - birth
            findings[rid] = Finding(
                code="H3",
                title="RID alto con fecha de creación anómalamente antigua",
                confidence=Confidence.LOW,
                detail=(
                    f"birth $SI ({birth}) muy anterior a la mediana de los "
                    f"vecinos por RID ({median_dt}), diferencia ~{delta.days} "
                    f"días. RID={rid}"
                ),
                false_positive_note=(
                    "El MFT reutiliza registros de archivos borrados: un RID "
                    "'viejo' puede alojar un archivo nuevo legítimamente. "
                    "Indicador ruidoso, úsalo solo como pista."
                ),
            )
    return findings


# ───────────────────────────────────────────────────────────────────────────
# Orquestador del análisis
# ───────────────────────────────────────────────────────────────────────────

@dataclass
class AnalysisConfig:
    system_install: Optional[datetime.datetime] = None
    now: Optional[datetime.datetime] = None
    include_directories: bool = False
    only_in_use: bool = False          # solo archivos existentes
    min_score: int = 1                 # umbral para reportar
    enable_h3: bool = True             # el de RID (ruidoso, opcional)


def analyze_records(records, config: Optional[AnalysisConfig] = None):
    """
    Aplica todas las heurísticas a una lista/iterable de MftRecord.

    Returns:
        (verdicts, stats)
        verdicts: lista de FileVerdict con score >= config.min_score
        stats: dict con métricas del análisis
    """
    if config is None:
        config = AnalysisConfig()

    verdicts = []
    birth_data = []     # para H3
    rec_index = {}      # record_number -> FileVerdict (para inyectar H3 luego)

    total = 0
    skipped_dirs = 0
    skipped_notinuse = 0

    for rec in records:
        total += 1

        if rec.is_directory and not config.include_directories:
            skipped_dirs += 1
            continue
        if config.only_in_use and not rec.in_use:
            skipped_notinuse += 1
            continue

        verdict = FileVerdict(
            record_number=rec.record_number,
            filename=rec.filename,
            is_directory=rec.is_directory,
            in_use=rec.in_use,
            **_snapshot_timestamps(rec),
        )

        # Heurísticas por-registro
        for fn in (
            h1_si_before_fn(rec),
            h2_zero_subseconds_si(rec),
            h4_created_after_modified(rec),
            h5_out_of_range(rec, config.system_install, config.now),
            h6_fn_zero_nanoseconds(rec),
        ):
            if fn:
                verdict.add(fn)

        # Recolectar datos para H3
        if rec.si_timestamps and rec.si_timestamps.created and not rec.is_directory:
            birth_data.append(
                (rec.record_number, rec.si_timestamps.created, rec.filename)
            )

        rec_index[rec.record_number] = verdict
        verdicts.append(verdict)

    # H3 a nivel global
    if config.enable_h3:
        h3_findings = h3_rid_birth_disorder(birth_data)
        for rid, finding in h3_findings.items():
            if rid in rec_index:
                rec_index[rid].add(finding)

    # Filtrar por umbral y ordenar por score descendente
    flagged = [v for v in verdicts if v.score >= config.min_score]
    flagged.sort(key=lambda v: v.score, reverse=True)

    stats = {
        "total_records_seen": total,
        "skipped_directories": skipped_dirs,
        "skipped_not_in_use": skipped_notinuse,
        "files_analyzed": len(verdicts),
        "files_flagged": len(flagged),
        "critical": sum(1 for v in flagged if v.suspicion_level == "CRÍTICO"),
        "high": sum(1 for v in flagged if v.suspicion_level == "ALTO"),
        "medium": sum(1 for v in flagged if v.suspicion_level == "MEDIO"),
        "low": sum(1 for v in flagged if v.suspicion_level == "BAJO"),
    }

    return flagged, stats
