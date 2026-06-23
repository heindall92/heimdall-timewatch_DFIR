# 🛡️ heimdall-timewatch

> **TimeStomp Detector** — Detección de manipulación de timestamps en NTFS mediante comparación `$STANDARD_INFORMATION` vs `$FILE_NAME` y corroboración cruzada con el USN Journal.
>
> *"El guardián que ve el tiempo."*

Creado por **Heindall** · Herramienta de DFIR / Blue Team para uso educativo y autorizado.

<p>
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg">
  <img alt="Python 3.8+" src="https://img.shields.io/badge/Python-3.8%2B-blue.svg">
  <img alt="Dependencias: 0" src="https://img.shields.io/badge/dependencias-0-success.svg">
  <img alt="MITRE ATT&CK T1070.006" src="https://img.shields.io/badge/MITRE%20ATT%26CK-T1070.006-red.svg">
  <img alt="Plataforma: Windows / Linux" src="https://img.shields.io/badge/plataforma-Windows%20%7C%20Linux-lightgrey.svg">
</p>

---

## ¿Qué hace?

`heimdall-timewatch` detecta **timestomping** — la técnica anti-forense con la que un atacante modifica las marcas de tiempo de un archivo para esconderlo de los análisis de línea temporal. Es una de las técnicas de evasión más usadas por actores de amenazas, mapeada en MITRE ATT&CK como **T1070.006 (Indicator Removal: Timestomp)**.

La herramienta parsea el Master File Table (MFT) de NTFS a bajo nivel, extrae los 8 timestamps MACE de cada archivo (4 del atributo `$SI`, modificable en user-mode, y 4 del `$FN`, que solo escribe el kernel) y aplica **6 heurísticas independientes** más una **corroboración con el USN Journal** para identificar archivos con marcas de tiempo manipuladas.

## Filosofía

**Honestidad forense ante todo.** Ningún indicador que esta herramienta reporta es prueba concluyente por sí solo. Cada hallazgo incluye su nivel de confianza y sus falsos positivos conocidos. Un detector que exagera su certeza es peor que ninguno. La corroboración entre múltiples artefactos siempre prevalece sobre una sola señal.

**Cero dependencias.** Solo biblioteca estándar de Python 3.8+. Una herramienta forense debe ser auditable, portable y ejecutable en un entorno aislado sin `pip install`.

## Instalación

```bash
git clone https://github.com/heindall92/heimdall-timewatch_DFIR.git
cd heimdall-timewatch_DFIR
# No requiere dependencias. Opcionalmente:
pip install -e .
```

> **Requisitos:** Python 3.8 o superior. Nada más. Funciona en Windows y Linux
> (la salida con color y caracteres Unicode está forzada a UTF-8, así que no se
> rompe en la consola de Windows).

## Uso rápido

### Modo laboratorio (pruébalo ya, sin MFT real)

```bash
python3 -m heimdall_timewatch.cli lab
```

Genera un MFT sintético con 6 casos de timestomping plantados y verifica que el detector los encuentra. Es tu "campo de tiro" para estudiar la técnica.

### Analizar un MFT real

```bash
# Extrae el $MFT primero con FTK Imager, MFTECmd, o:
#   icat -o <offset> imagen.dd 0 > \$MFT

python3 -m heimdall_timewatch.cli scan -m \$MFT

# Con corroboración USN Journal (recomendado):
python3 -m heimdall_timewatch.cli scan -m \$MFT --usn \$J --html informe.html

# Con fecha de instalación del SO (mejora la heurística H5):
python3 -m heimdall_timewatch.cli scan -m \$MFT --system-install 2024-01-15

# Exportar a varios formatos:
python3 -m heimdall_timewatch.cli scan -m \$MFT --json out.json --csv out.csv --html out.html
```

### Volcar timestamps a CSV (sin juzgar)

```bash
python3 -m heimdall_timewatch.cli parse -m \$MFT -o timestamps.csv
```

## Las heurísticas

| Código | Detecta | Confianza |
|--------|---------|-----------|
| **H1** | `$SI` anterior a `$FN` (retroceso temporal) | Media → Alta si el desfase supera 30 días |
| **H2** | Subsegundos de `$SI` en `.0000000` (herramienta automática) | Baja |
| **H3** | RID alto con fecha de creación anómalamente antigua | Baja |
| **H4** | `created` posterior a `modified` (imposible lógico) | Media |
| **H5** | Timestamp en el futuro o anterior a la instalación del SO | Media |
| **H6** | Subsegundos de `$FN` en cero (manipulación avanzada de `$FN`) | Media |
| **USN** | El USN Journal contradice la fecha de creación `$SI` | **Alta** |

## Cómo extraer los artefactos de un sistema

```bash
# Con FTK Imager (GUI): Add Evidence Item → Logical Drive → exportar
#   $MFT y $Extend\$UsnJrnl:$J desde la raíz del volumen.

# Con MFTECmd (Eric Zimmerman):
MFTECmd.exe -f C:\$MFT --csv salida

# Desde Linux sobre una imagen montada:
icat -o 2048 disco.dd 0 > \$MFT
```

## Limitaciones honestas

- **El método `$SI` vs `$FN` tiene puntos ciegos.** Si el atacante renombra o mueve el archivo en el mismo volumen después de timestompear, Windows copia el `$SI` manipulado al `$FN` y H1 deja de dispararse. Por eso la corroboración con USN es clave.
- **El USN Journal es circular.** Si el evento de creación ya rotó fuera del journal, no habrá corroboración. Ausencia de evidencia no es evidencia de ausencia.
- **Falsos positivos legítimos:** instaladores que tocan `$SI`, archivos extraídos de ZIP (subsegundos truncados), copias que preservan mtime, relojes mal configurados. Cada hallazgo los documenta.

## Estructura

```
heimdall-timewatch/
├── heimdall_timewatch/
│   ├── __init__.py
│   ├── mft_parser.py     # parser de bajo nivel del MFT
│   ├── detector.py       # motor de las 6 heurísticas
│   ├── usn_journal.py     # parser USN + corroboración
│   ├── reporting.py       # consola/JSON/CSV/HTML
│   ├── labgen.py          # generador de MFT de laboratorio
│   └── cli.py             # interfaz de línea de comandos
├── requirements.txt
├── setup.py
└── README.md
```

## Aviso legal

Para uso en sistemas propios, laboratorios autorizados (HTB, THM, máquinas de práctica) o auditorías DFIR con autorización explícita. El análisis forense de sistemas ajenos sin autorización puede ser ilegal. Esta herramienta existe para **detectar** la actividad anti-forense, no para realizarla.

## Licencia

Distribuido bajo licencia **MIT**. Eres libre de usar, modificar y redistribuir la herramienta, conservando el aviso de copyright. Ver el archivo [LICENSE](LICENSE) para el texto completo.

## Contribuir

Las contribuciones son bienvenidas: nuevas heurísticas, parsers de artefactos adicionales (LNK, Prefetch, $LogFile), o casos de laboratorio. Abre un *issue* para discutir cambios grandes antes de un *pull request*. Mantén el principio de **cero dependencias** y documenta los falsos positivos de cada heurística nueva.

---

*heimdall-timewatch · creado por Heindall · 2026 · MIT License*
