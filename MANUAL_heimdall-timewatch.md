# 🛡️ heimdall-timewatch — Manual Completo del Detector de Timestomping
**Para:** Máster en Ciberseguridad — Evolve Academy + Blue Team / DFIR
**Nivel:** Desde la teoría NTFS hasta el análisis forense real
**Herramienta:** heimdall-timewatch (creada por Heindall) — detección de timestomping en NTFS
**Plataformas de práctica:** Cualquier imagen NTFS, máquinas Windows de HTB/THM, el laboratorio integrado
**Referencia:** Brian Carrier "File System Forensic Analysis" + SANS DFIR + inversecos + Magnet Forensics + MITRE ATT&CK T1070.006

> ⚠️ **AVISO LEGAL:** Esta es una herramienta DEFENSIVA / de investigación forense. Úsala en sistemas propios, laboratorios autorizados (HTB, THM, máquinas de práctica) o auditorías DFIR con autorización explícita. El análisis forense de sistemas ajenos sin autorización puede vulnerar los arts. 197 y 197 bis del Código Penal español. heimdall-timewatch existe para DETECTAR la manipulación anti-forense, nunca para realizarla.

---

## 📑 Índice

1. [¿Qué es el timestomping y por qué importa?](#1-qué-es-el-timestomping)
2. [Teoría NTFS — los 8 timestamps que casi nadie conoce](#2-teoría-ntfs)
3. [El secreto: $SI vs $FN (quién puede escribir qué)](#3-el-secreto-si-vs-fn)
4. [Qué hace heimdall-timewatch — visión general](#4-qué-hace-la-herramienta)
5. [Instalación y primer contacto](#5-instalación)
6. [El modo laboratorio — tu campo de tiro](#6-el-modo-laboratorio)
7. [Las 6 heurísticas explicadas una a una](#7-las-6-heurísticas)
8. [La corroboración con el USN Journal](#8-corroboración-usn)
9. [El sistema de puntuación y confianza](#9-puntuación-y-confianza)
10. [Cómo extraer el MFT y el USN de un sistema real](#10-extraer-artefactos)
11. [Analizar un caso real paso a paso](#11-caso-real-paso-a-paso)
12. [Interpretar los resultados como un analista](#12-interpretar-resultados)
13. [Los límites honestos — lo que NO detecta](#13-límites-honestos)
14. [Arquitectura del código](#14-arquitectura-del-código)
15. [Perspectiva Red Team — cómo se evade esto](#15-perspectiva-red-team)
16. [Cheat Sheet](#16-cheat-sheet)

---

## 1. ¿Qué es el timestomping?

### La idea central

**Timestomping** es el acto de modificar las marcas de tiempo (timestamps) de un archivo para engañar a un investigador forense. Es una técnica **anti-forense** de la categoría "trail obfuscation" (ofuscación de rastro), y está catalogada en MITRE ATT&CK como **T1070.006**.

### La analogía — el ladrón que cambia la fecha del fichaje

```
Imagina una oficina con un libro de fichajes donde cada empleado anota la hora
a la que entra y sale. Un día hay un robo a las 3 de la madrugada.

El ladrón, que es un empleado, sabe que la policía revisará el libro buscando
quién estuvo allí a las 3 AM. Así que hace una cosa astuta:

  → Coge SU línea del libro y reescribe su hora de entrada y salida,
    poniendo "entré a las 9:00 y salí a las 17:00 del día ANTERIOR".

  → Ahora, cuando la policía filtre por "quién estuvo a las 3 AM",
    su nombre no aparece. Se ha borrado de la línea temporal del crimen.

Eso es timestomping: el atacante reescribe las marcas de tiempo de sus
archivos maliciosos (su malware, sus herramientas) para que, cuando el
forense filtre por "qué se creó/modificó durante el incidente", esos
archivos no aparezcan. Se esconden cambiando su fecha.

PERO... y aquí está la clave de nuestra herramienta:
  En esa oficina hay un SEGUNDO libro, en la recepción, que SOLO el guardia
  de seguridad puede escribir. El ladrón no tiene acceso a él. Y ese segundo
  libro registró la hora REAL. Comparar los dos libros delata la mentira.

Ese "segundo libro" en NTFS es el atributo $FILE_NAME. Y compararlo con el
que el atacante SÍ puede tocar ($STANDARD_INFORMATION) es la base de
heimdall-timewatch.
```

### Por qué un atacante hace timestomping

```
El objetivo principal: RETRASAR LA DETECCIÓN.

  → Cuando salta una alerta, el analista forense establece una "ventana
    temporal del incidente" (p.ej. "actividad sospechosa el 15 de mayo").
  → Luego filtra todos los archivos creados/modificados en esa ventana.
  → El malware con timestamp del 15 de mayo aparecería inmediatamente.
  → Pero si el atacante lo retrocede a "enero de 2019", el filtro no lo pilla.
  → El archivo malicioso se camufla entre los archivos viejos legítimos del
    sistema, y el analista puede tardar semanas en encontrarlo (o nunca).

Es una de las primeras cosas que hace un atacante competente tras desplegar
su persistencia: esconder sus artefactos en el tiempo.
```

### Por qué construir un detector es valioso para tu carrera

```
✅ El timestomping es DIARIO en incidentes reales (APTs, ransomware, etc.).
✅ Saber detectarlo es una habilidad core de DFIR / Blue Team / SOC.
✅ Entender la técnica te hace mejor en Red Team (sabes qué deja rastro).
✅ Es un proyecto de portfolio que demuestra que entiendes NTFS a bajo nivel,
   no solo que sabes ejecutar herramientas de terceros.
✅ Conecta con tu gap identificado: experiencia ofensiva sólida, y este
   proyecto refuerza el lado defensivo/forense.
```

---

## 2. Teoría NTFS

### El MFT — la columna vertebral de NTFS

```
NTFS (el sistema de ficheros de Windows) organiza TODO en una estructura
central llamada MFT (Master File Table). Piensa en el MFT como la AGENDA
TELEFÓNICA del disco: una entrada por cada archivo y carpeta del volumen.

  → Cada entrada del MFT es un "registro FILE" de 1024 bytes.
  → Cada registro contiene ATRIBUTOS: el nombre del archivo, su tamaño,
    sus permisos, sus timestamps, y punteros a dónde están los datos.

Cuando creas un archivo → se añade un registro al MFT.
Cuando lo borras → el registro se marca como "no en uso" (pero sigue ahí,
  por eso se pueden recuperar archivos borrados).
```

### Los dos atributos de timestamps

```
Cada archivo tiene DOS atributos distintos que almacenan timestamps:

┌──────────────────────────────────────────────────────────────────────┐
│  ATRIBUTO                  SHORTHAND   QUIÉN PUEDE ESCRIBIRLO          │
├──────────────────────────────────────────────────────────────────────┤
│  $STANDARD_INFORMATION     $SI         Cualquier proceso en user-mode  │
│  $FILE_NAME                $FN         SOLO el kernel de Windows        │
└──────────────────────────────────────────────────────────────────────┘

Esta distinción es LA BASE de toda la ciencia forense de timestamps.
```

### Los 8 timestamps (4 + 4) — MACE

```
Cada uno de los dos atributos contiene 4 timestamps, conocidos como MACE
(a veces MACB). En total, 8 timestamps por archivo:

  M - Modified    (cuándo cambió el CONTENIDO del archivo)
  A - Accessed    (cuándo se ACCEDIÓ por última vez)
  C - Changed     (cuándo cambió el REGISTRO MFT — "MFT modified")
  E - Born/Created(cuándo se CREÓ el archivo — "birth")

  Nota: el orden de las siglas varía según la fuente. Lo importante es que
  son cuatro: creación, modificación, modificación-del-MFT, y acceso.

  $SI tiene sus 4 MACE  ← los que ves en Windows Explorer / cmd / PowerShell
  $FN tiene sus 4 MACE  ← los que solo escribe el kernel

Formato de almacenamiento:
  Cada timestamp es un valor de 64 bits = nº de intervalos de 100 nanosegundos
  transcurridos desde el 1 de enero de 1601 a las 00:00 UTC (el "epoch" de
  Windows FILETIME). heimdall-timewatch decodifica este formato en mft_parser.py.
```

### Por qué hay subsegundos (y por qué importan)

```
Como el timestamp se guarda en intervalos de 100 ns, tiene una precisión
altísima: hasta diez millonésimas de segundo.

  Un timestamp normal generado por Windows se ve así (con subsegundos):
    2026-05-28 14:30:17.8493621

  Pero muchas herramientas de timestomping solo permiten precisión al segundo,
  así que dejan los subsegundos en cero:
    2026-05-28 14:30:17.0000000
                       ^^^^^^^^
                       Bandera roja: precisión "demasiado redonda"

Esta es la base de las heurísticas H2 y H6 de heimdall-timewatch.
```

---

## 3. El secreto: $SI vs $FN

### La regla de oro de la detección

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   $SI lo puede modificar CUALQUIER proceso en user-mode.             │
│   → Es lo que las herramientas de timestomping ATACAN.               │
│   → Es lo que Windows Explorer te MUESTRA.                           │
│                                                                      │
│   $FN SOLO lo escribe el KERNEL de Windows.                          │
│   → Ninguna herramienta anti-forense CONOCIDA puede modificarlo      │
│     directamente desde user-mode.                                    │
│   → Por eso es un testigo FIABLE.                                    │
│                                                                      │
│   ⚡ SI los timestamps de $SI NO COINCIDEN con los de $FN en el      │
│      mismo archivo → ese archivo fue TIMESTOMPEADO.                  │
│                                                                      │
└────────────────────────────────────────────────────────────────────┘
```

### Cómo se ve en la práctica

```
Archivo LIMPIO (timestamps coherentes):
  $SI.created:  2026-05-28 14:30:17.849
  $FN.created:  2026-05-28 14:30:17.849   ← coinciden ✓

Archivo TIMESTOMPEADO (el atacante retrocedió el $SI):
  $SI.created:  2019-03-15 10:00:00.000   ← lo que ve el analista despistado
  $FN.created:  2026-05-28 14:30:17.849   ← la VERDAD que escribió el kernel
                ^^^^^^^^^^^^^^^^^^^^^^^^
                ¡7 años de diferencia! → timestomping evidente
```

### El detalle honesto que debes conocer (el "mito")

```
⚠️ El método $SI vs $FN NO es infalible. Hay un punto ciego importante:

  Cuando un archivo se RENOMBRA o se MUEVE dentro del mismo volumen, Windows
  COPIA los timestamps de $SI al $FN. Es comportamiento normal del sistema.

  Esto significa que un atacante astuto puede:
    1. Timestompear el $SI (retroceder la fecha).
    2. Renombrar el archivo (o moverlo en el mismo volumen).
    3. → Windows copia el $SI manipulado al $FN.
    4. → Ahora $SI y $FN COINCIDEN (ambos con la fecha falsa).
    5. → La comparación H1 ya NO detecta nada (falso negativo).

  Además, herramientas avanzadas como SetMACE (en sistemas sin PatchGuard)
  SÍ pueden tocar el $FN directamente.

POR ESO heimdall-timewatch no se queda solo en H1. Usa 6 heurísticas +
corroboración con USN Journal. Cuantos más ángulos, más difícil es evadir
TODOS a la vez. Y por eso la herramienta es HONESTA sobre la confianza de
cada hallazgo: nunca te dice "esto es timestomping seguro", te dice "esto es
sospechoso por estas razones, con esta confianza, y estos falsos positivos".
```

---

## 4. Qué hace la herramienta

### Visión general del flujo

```
        ┌─────────────┐
        │  Fichero    │  (extraído con FTK Imager, MFTECmd, icat...)
        │   $MFT      │
        └──────┬──────┘
               │
               ▼
    ┌──────────────────────┐
    │  mft_parser.py       │  Lee registros de 1024 b, extrae $SI y $FN,
    │  (parsing bajo nivel)│  decodifica los 8 timestamps FILETIME
    └──────────┬───────────┘
               │  MftRecord (datos crudos, sin juzgar)
               ▼
    ┌──────────────────────┐
    │  detector.py         │  Aplica las 6 heurísticas (H1-H6),
    │  (motor heurístico)  │  asigna score y confianza a cada archivo
    └──────────┬───────────┘
               │  FileVerdict (con findings y puntuación)
               ▼
    ┌──────────────────────┐      ┌─────────────┐
    │  usn_journal.py      │◄─────│  Fichero    │  (opcional pero
    │  (corroboración)     │      │   $J (USN)  │   muy recomendado)
    └──────────┬───────────┘      └─────────────┘
               │  FileVerdict enriquecido (corroborado = confianza ALTA)
               ▼
    ┌──────────────────────┐
    │  reporting.py        │  Consola con color / JSON / CSV / HTML
    └──────────────────────┘
```

### Las tres formas de usarla

```
1. scan   → analiza un $MFT real (con o sin $USN). El uso principal.
2. lab    → genera un MFT sintético con casos plantados y los detecta.
            Tu campo de tiro para aprender sin sistema real.
3. parse  → vuelca los timestamps de un MFT a CSV sin juzgar. Útil para
            inspección manual o alimentar otras herramientas (Timeline Explorer).
```

---

## 5. Instalación

### Requisitos

```bash
# Solo necesitas Python 3.8 o superior. CERO dependencias externas.
python3 --version   # debe ser >= 3.8

# Esto es deliberado: una herramienta forense debe ser auditable y ejecutable
# en un entorno aislado sin pip install. Cero dependencias = cero riesgo de
# supply-chain y máxima confianza en un entorno DFIR.
```

### Puesta en marcha

```bash
# Clonar / descomprimir el proyecto
cd heimdall-timewatch

# Opción A: ejecutar directamente como módulo
python3 -m heimdall_timewatch.cli --version

# Opción B: instalar como comando del sistema
pip install -e .
heimdall-timewatch --version
```

---

## 6. El modo laboratorio

### Tu campo de tiro seguro

Antes de tocar un MFT real, usa el modo laboratorio. Genera un MFT sintético con 6 casos de timestomping plantados (uno por cada heurística) y verifica que el detector los encuentra. Es la mejor forma de **ver la herramienta en acción y entender cada heurística**.

```bash
python3 -m heimdall_timewatch.cli lab
```

### Qué hace, paso a paso

```
1. Genera un MFT sintético con ~200 archivos LIMPIOS (timestamps coherentes).
2. Planta 6 archivos maliciosos con timestamps manipulados:
   · MFT #216: evil_backdoor.exe  → H1 (clásico: $SI 2019 vs $FN 2026)
   · MFT #217: mimikatz_renamed.exe → H2 (subsegundos $SI en cero)
   · MFT #218: tampered_config.dll → H4 (created > modified)
   · MFT #219: future_file.bin     → H5 (fecha en 2030)
   · MFT #220: setmace_victim.sys  → H6 (subsegundos $FN en cero)
   · MFT #221: rootkit.dat         → H1+H2 (combinado, score alto)
3. Analiza el MFT con todas las heurísticas.
4. Imprime los hallazgos ordenados por sospecha.
5. VERIFICA: comprueba que detectó los 6 casos plantados (6/6).
```

### Salida esperada (resumen)

```
═══ VERIFICACIÓN (¿detectamos lo plantado?) ═══
  ✓ DETECTADO  MFT #216 — H1: timestomping clásico ($SI<$FN)
  ✓ DETECTADO  MFT #217 — H2: subsegundos $SI en cero
  ✓ DETECTADO  MFT #218 — H4: created > modified
  ✓ DETECTADO  MFT #219 — H5: fecha en el futuro
  ✓ DETECTADO  MFT #220 — H6: subsegundos $FN en cero
  ✓ DETECTADO  MFT #221 — H1+H2: combinado (clásico + redondeo)

  Detección: 6/6 casos plantados
```

### Generar un informe HTML del laboratorio

```bash
python3 -m heimdall_timewatch.cli lab --html informe_lab.html
# Abre informe_lab.html en el navegador para ver el informe visual.
```

---

## 7. Las 6 heurísticas

Cada heurística detecta una "huella" distinta del timestomping. Ninguna es concluyente sola; juntas forman una red difícil de evadir.

### H1 — $SI anterior a $FN (el método clásico)

```
QUÉ DETECTA:
  Cuando $SI.created (o $SI.modified) es ANTERIOR a su equivalente en $FN.
  Como $FN solo lo escribe el kernel, si $SI es más antiguo → alguien
  retrocedió el $SI (timestomping clásico).

CONFIANZA: Media → ALTA si el retroceso supera 30 días.
  Un desfase de minutos puede ser ruido; un retroceso de meses/años es
  muy difícil de explicar sin manipulación deliberada.

FALSO NEGATIVO: si el atacante renombró/movió el archivo tras timestompear,
  $SI se copió a $FN y H1 no dispara.
FALSO POSITIVO: algunos instaladores modifican $SI legítimamente.

EJEMPLO REAL (del laboratorio):
  evil_backdoor.exe
  $SI.created: 2019-03-15  ←  $FN.created: 2026-05-28  →  7 años de desfase
```

### H2 — Subsegundos de $SI en cero

```
QUÉ DETECTA:
  Cuando varios timestamps de $SI tienen los subsegundos en .0000000.
  Muchas herramientas de timestomping solo manejan precisión al segundo.

CONFIANZA: Baja (es un indicador de apoyo, no concluyente).

FALSO POSITIVO: archivos extraídos de ZIP y algunos instaladores truncan
  los subsegundos legítimamente.

EJEMPLO: mimikatz_renamed.exe con todos los $SI en .0000000
```

### H3 — RID alto con creación anómalamente antigua

```
QUÉ DETECTA:
  Los números de registro del MFT (RID) crecen secuencialmente: archivos más
  antiguos suelen tener RIDs más bajos. Si un archivo tiene un RID alto pero
  una fecha de creación $SI muy anterior a la mediana de sus vecinos por RID,
  su birth time pudo ser retrocedido.

CONFIANZA: Baja (el MFT reutiliza registros de archivos borrados → ruidoso).

CÓMO LO CALCULA: ventana deslizante sobre los RIDs, mediana de las fechas de
  creación de los vecinos, y marca los outliers hacia el pasado.

ÚSALO COMO PISTA, no como acusación.
```

### H4 — created posterior a modified (imposible lógico)

```
QUÉ DETECTA:
  Un archivo no puede modificarse ANTES de crearse. Si $SI.created es
  posterior a $SI.modified por más de 60 segundos → manipulación descuidada.

CONFIANZA: Media.

FALSO POSITIVO: copias y restauraciones de backup que preservan el mtime
  original sobre un archivo recién creado.

EJEMPLO: tampered_config.dll (created a las 16:00, modified a las 10:00)
```

### H5 — Timestamp fuera de rango

```
QUÉ DETECTA:
  · Fechas en el FUTURO respecto al momento del análisis (>24h de margen).
  · Fechas ANTERIORES a la instalación del SO (si la proporcionas con
    --system-install).

CONFIANZA: Media.

FALSO POSITIVO: relojes mal configurados, errores de zona horaria, archivos
  copiados de sistemas más antiguos.

EJEMPLO: future_file.bin con fecha de 2030.
```

### H6 — Subsegundos de $FN en cero (manipulación avanzada)

```
QUÉ DETECTA:
  El kernel NO redondea los subsegundos al escribir $FN. Si los timestamps de
  $FN tienen subsegundos en cero → posible manipulación avanzada que tocó el
  $FN (p.ej. SetMACE en sistemas sin PatchGuard), algo de por sí anómalo.

CONFIANZA: Media (tocar $FN ya es inusual, merece investigación).

EJEMPLO: setmace_victim.sys con todos los $FN en .0000000
```

---

## 8. Corroboración USN

### Qué es el USN Journal

```
El USN Journal ($Extend\$UsnJrnl:$J) es un registro de NTFS que anota CADA
operación sobre archivos: creación, escritura, rename, borrado, etc. Cada
entrada lleva su propio timestamp, generado por el sistema en el momento real
del evento.

LA CLAVE: es un artefacto INDEPENDIENTE del $SI y del $FN.
```

### Por qué es la corroboración más potente

```
Si un archivo tiene:
  $SI.created: 2019  (sospechoso por H1)
  Y el USN Journal registra su FILE_CREATE en: 2026

  → El USN, generado por el sistema en el momento del evento real, CONTRADICE
    directamente la fecha falsa del $SI.
  → Esto es evidencia INDEPENDIENTE y difícil de manipular sin privilegios y
    herramientas específicas.
  → heimdall-timewatch añade un hallazgo de confianza ALTA y dispara el score.

Como dice la doctrina DFIR: la corroboración entre múltiples artefactos
SIEMPRE prevalece sobre una sola fuente.
```

### Cómo se usa

```bash
# Proporciona el $J extraído junto al $MFT
python3 -m heimdall_timewatch.cli scan -m \$MFT --usn \$J --html informe.html

# heimdall-timewatch:
#  1. Analiza el MFT con las 6 heurísticas.
#  2. Construye un índice de creación desde los FILE_CREATE del USN.
#  3. Para cada archivo ya sospechoso de retroceso (H1/H3/H4/H5), comprueba
#     si el USN tiene un FILE_CREATE que contradiga el $SI.
#  4. Si lo hay → añade hallazgo USN de confianza ALTA y sube el score.
```

### El efecto en la práctica (verificado)

```
evil_backdoor.exe:
  Score ANTES de corroborar:    60  (nivel ALTO)
  + hallazgo USN (confianza ALTA): +50
  Score DESPUÉS de corroborar:  110 (nivel CRÍTICO)

La corroboración convierte una "sospecha fuerte" en una "certeza forense".
```

### El límite honesto

```
⚠️ El USN Journal es CIRCULAR y de tamaño limitado: los eventos antiguos se
   sobrescriben. Si el FILE_CREATE del archivo ya rotó fuera del journal, no
   habrá corroboración disponible.

   Ausencia de corroboración ≠ ausencia de manipulación. Su PRESENCIA es muy
   fiable; su ausencia simplemente no aporta información.
```

---

## 9. Puntuación y confianza

### El sistema de score

```
Cada heurística que dispara suma puntos según su nivel de confianza:

  Confianza ALTA   → +50 puntos
  Confianza MEDIA  → +25 puntos
  Confianza BAJA   → +10 puntos

El score total de un archivo determina su nivel de sospecha:

  Score >= 70   →  CRÍTICO   (múltiples indicadores fuertes o corroboración)
  Score >= 45   →  ALTO
  Score >= 20   →  MEDIO
  Score >   0   →  BAJO
  Score == 0    →  LIMPIO
```

### Por qué este diseño es forense-correcto

```
✅ Un solo indicador débil (BAJO) no genera alarma → evita ruido.
✅ Varios indicadores juntos elevan el nivel → la acumulación es señal.
✅ La corroboración USN (ALTA) puede por sí sola llevar a CRÍTICO → premia
   la evidencia independiente.
✅ NUNCA dice "timestomping confirmado" sin más → siempre muestra el porqué,
   la confianza y los falsos positivos de cada hallazgo.

Esto refleja cómo trabaja un analista real: no es un veredicto binario, es una
acumulación de evidencia ponderada por su fiabilidad.
```

---

## 10. Extraer artefactos

### Con FTK Imager (GUI, lo más sencillo)

```
1. Abrir FTK Imager como Administrador.
2. File → Add Evidence Item → Logical Drive → seleccionar el volumen (C:).
3. En el árbol de la izquierda, expandir el volumen.
4. Los metadatos NTFS aparecen en la raíz con prefijo $:
   · $MFT
   · $Extend\$UsnJrnl  (el stream $J)
5. Clic derecho → Export Files → guardar.
```

### Con MFTECmd (Eric Zimmerman, CLI)

```bash
# Extraer y parsear el MFT a CSV (MFTECmd ya hace su propio análisis,
# pero también puedes pasarle el $MFT crudo a heimdall-timewatch)
MFTECmd.exe -f "C:\$MFT" --csv salida --csvf mft.csv

# Para heimdall-timewatch necesitas el $MFT CRUDO, que puedes obtener con
# FTK Imager o copiándolo con herramientas que accedan a archivos bloqueados.
```

### Desde Linux sobre una imagen de disco

```bash
# Si tienes una imagen .dd / .raw de un disco NTFS:
# 1. Localizar el offset de la partición NTFS
mmls disco.dd

# 2. Extraer el $MFT (inode 0 en NTFS) con icat de The Sleuth Kit
icat -o <offset_sectores> disco.dd 0 > \$MFT

# 3. Extraer el USN Journal
#    Primero localizar su inode:
fls -o <offset> disco.dd -p -r | grep -i usnjrnl
#    Luego extraer el stream $J por su inode:
icat -o <offset> disco.dd <inode_del_J> > \$J
```

### Analizar lo extraído

```bash
python3 -m heimdall_timewatch.cli scan -m \$MFT --usn \$J \
  --system-install 2024-01-15 \
  --html informe.html --json hallazgos.json
```

---

## 11. Caso real paso a paso

### Escenario

```
Te dan una imagen de un servidor Windows comprometido. Saltó una alerta el
15 de mayo de 2026. Sospechas que el atacante dejó malware pero lo escondió
con timestomping. Objetivo: encontrar los archivos manipulados.
```

### Paso 1 — Extraer los artefactos

```bash
mmls servidor.dd
# Partición NTFS en offset 2048

icat -o 2048 servidor.dd 0 > \$MFT
fls -o 2048 servidor.dd -p -r | grep -i usnjrnl   # localizar el $J
icat -o 2048 servidor.dd <inode> > \$J
```

### Paso 2 — Análisis inicial

```bash
python3 -m heimdall_timewatch.cli scan -m \$MFT --usn \$J \
  --system-install 2024-01-10 \
  --html caso_servidor.html --json caso_servidor.json
```

### Paso 3 — Leer el resumen de consola

```
Te fijas primero en:
  → CRÍTICOS y ALTOS: estos son tus principales sospechosos.
  → Archivos con corroboración USN: evidencia independiente, máxima prioridad.
  → Archivos .exe/.dll/.sys en rutas inusuales con score alto.
```

### Paso 4 — Investigar cada CRÍTICO

```
Para cada archivo CRÍTICO/ALTO:
  1. Anota su ruta y nombre.
  2. Mira QUÉ heurísticas dispararon y la diferencia $SI vs $FN.
  3. Si hay corroboración USN → la fecha del USN es la fecha REAL de creación.
  4. Cruza esa fecha real con la ventana del incidente (15 de mayo).
     → Si el USN dice que se creó el 15 de mayo pero el $SI dice 2019,
       acabas de encontrar malware timestompeado durante el incidente.
```

### Paso 5 — Documentar

```
En tu informe forense:
  → "El archivo C:\Windows\Temp\svchost.exe presenta timestomping: su $SI
     indica creación en 2019, pero el $FN (kernel) y el USN Journal coinciden
     en una creación real el 2026-05-15 a las 03:42 UTC, dentro de la ventana
     del incidente. Heurísticas disparadas: H1 (retroceso masivo), corroborado
     por USN Journal (confianza alta)."
  → Adjunta el HTML/JSON de heimdall-timewatch como evidencia.
```

---

## 12. Interpretar resultados

### La mentalidad correcta

```
heimdall-timewatch NO te da un veredicto binario. Te da EVIDENCIA PONDERADA.
Tu trabajo como analista es interpretarla:

  CRÍTICO con corroboración USN → casi seguro timestomping. Investiga a fondo.
  ALTO sin corroboración        → sospecha fuerte. Busca más contexto.
  MEDIO                         → puede ser legítimo. Corrobora antes de concluir.
  BAJO                          → probablemente ruido. Anota pero no te obsesiones.
```

### Reducir falsos positivos

```
Cosas que generan falsos positivos legítimos (tenlos en cuenta):
  → Instaladores de software (tocan $SI de muchos archivos a la vez).
  → Archivos extraídos de ZIP/RAR (subsegundos truncados → H2).
  → Copias de archivos entre volúmenes (timestamps preservados).
  → Backups restaurados (mtime original sobre archivos nuevos → H4).
  → Relojes del sistema mal configurados (→ H5).

REGLA: si MUCHOS archivos de la MISMA carpeta disparan la MISMA heurística
con BAJA confianza, probablemente sea un instalador o una extracción ZIP, no
un ataque. El timestomping malicioso suele ser PUNTUAL (pocos archivos
concretos), no masivo.
```

### Priorizar

```
Orden de prioridad para investigar:
  1. CRÍTICOS con corroboración USN.
  2. Ejecutables (.exe/.dll/.sys) con score ALTO en rutas sospechosas
     (Temp, ProgramData, AppData, carpetas con nombres aleatorios).
  3. Archivos cuya fecha real (USN) cae dentro de la ventana del incidente.
  4. El resto, por score descendente.
```

---

## 13. Límites honestos

Una herramienta forense que miente sobre lo que puede hacer es peligrosa. Estos son los límites reales de heimdall-timewatch:

```
❌ NO detecta timestomping perfecto con rename posterior.
   Si el atacante timestompea Y LUEGO renombra/mueve el archivo en el mismo
   volumen, Windows copia el $SI al $FN y H1 no dispara. Mitigación: las otras
   heurísticas (H2, H4, H6) y sobre todo el USN Journal pueden pillarlo igual.

❌ NO funciona sin el $MFT.
   Necesita el Master File Table. Si solo tienes archivos sueltos sin la
   estructura NTFS, no hay $SI/$FN que comparar.

❌ La corroboración USN depende de que el evento siga en el journal.
   El USN es circular; eventos viejos se sobrescriben. Si el FILE_CREATE rotó,
   no hay corroboración (pero su ausencia no prueba inocencia).

❌ Genera falsos positivos con software legítimo.
   Instaladores, extracciones ZIP, copias y backups pueden disparar
   heurísticas. Por eso cada hallazgo documenta sus falsos positivos.

❌ NO es prueba judicial por sí sola.
   Es una herramienta de TRIAGE e investigación. Sus hallazgos deben
   corroborarse con otros artefactos (EDR, logs, PCAP, $LogFile) antes de
   conclusiones formales.

❌ Solo soporta USN_RECORD_V2 (el formato más común).
   V3/V4 usan referencias de 128 bits y no están implementados (V2 cubre la
   inmensa mayoría de los casos reales).

LO QUE SÍ HACE BIEN:
  ✓ Triage rápido de timestomping en un volumen NTFS completo.
  ✓ Detección multi-ángulo difícil de evadir en su totalidad.
  ✓ Corroboración con evidencia independiente (USN).
  ✓ Honestidad: cada hallazgo con su confianza y sus falsos positivos.
```

---

## 14. Arquitectura del código

```
heimdall_timewatch/
│
├── mft_parser.py     EL LECTOR
│   · Lee registros FILE de 1024 b del $MFT.
│   · Aplica el fixup (Update Sequence Array) de NTFS.
│   · Extrae atributos $SI (0x10) y $FN (0x30).
│   · Decodifica los 8 timestamps FILETIME → datetime UTC.
│   · NO juzga: solo extrae datos crudos y fiables.
│
├── detector.py       EL JUEZ
│   · Las 6 heurísticas (H1-H6), cada una con su confianza y falsos positivos.
│   · Sistema de score y niveles de sospecha.
│   · H3 se evalúa a nivel global (ventana deslizante de RIDs).
│   · Orquestador analyze_records().
│
├── usn_journal.py    EL TESTIGO INDEPENDIENTE
│   · Parsea el USN Journal ($J), formato USN_RECORD_V2.
│   · Construye índice de creación (FILE_CREATE events).
│   · corroborate(): cruza hallazgos con el USN, añade confianza ALTA.
│
├── reporting.py      EL NARRADOR
│   · Consola con color ANSI (estilo Heindall).
│   · Exportadores JSON (SIEM), CSV (Excel/Timeline), HTML (informe visual).
│
├── labgen.py         EL CAMPO DE TIRO
│   · Genera un $MFT sintético con casos de timestomping etiquetados.
│   · Construye registros FILE válidos byte a byte.
│
└── cli.py            EL DIRECTOR
    · Subcomandos scan / lab / parse.
    · Orquesta todo el flujo y la salida.
```

### Por qué esta separación

```
Cada módulo tiene UNA responsabilidad (principio de responsabilidad única):
  → El parser no juzga (solo lee).
  → El detector no lee disco ni imprime (solo razona sobre datos).
  → El reporting no decide nada (solo presenta).

Esto hace el código auditable, testeable y extensible. Añadir una heurística
nueva = añadir una función en detector.py, sin tocar nada más. Y en forense,
un código auditable es un código en el que se puede confiar.
```

---

## 15. Perspectiva Red Team

Entender cómo se EVADE este detector te hace mejor en ambos lados.

```
CÓMO UN ATACANTE EVADIRÍA heimdall-timewatch (y qué le cuesta):

1. Rename tras timestomping
   → Timestompear el $SI y luego renombrar/mover en el mismo volumen para que
     Windows copie $SI a $FN. Derrota H1.
   → COSTE: no derrota el USN Journal (que registró el FILE_CREATE real ni la
     operación de rename con su timestamp).

2. Igualar subsegundos
   → Usar una herramienta que ponga subsegundos realistas (no .0000000).
     Derrota H2 y H6.
   → COSTE: requiere herramientas más sofisticadas; muchas no lo hacen.

3. Coherencia created < modified
   → Asegurarse de que las fechas falsas son lógicamente coherentes. Derrota H4.
   → COSTE: más trabajo manual; los kits automáticos suelen fallar aquí.

4. Limpiar el USN Journal
   → Borrar o truncar el $UsnJrnl para eliminar la corroboración.
   → COSTE: requiere privilegios altos, y el ACTO de limpiar el USN es en sí
     mismo un IOC ruidoso (otras herramientas lo detectan).

LA LECCIÓN PARA AMBOS LADOS:
  → Red Team: evadir UN indicador es fácil; evadirlos TODOS a la vez +
    el USN + el $LogFile + la telemetría EDR es muy difícil. El timestomping
    perfecto es más raro de lo que parece.
  → Blue Team: por eso la detección multi-ángulo + corroboración funciona.
    Nunca confíes en una sola señal; la fuerza está en la acumulación.
```

---

## 16. Cheat Sheet

```
═══════════════════════════════════════════════════════════════════
USO BÁSICO
═══════════════════════════════════════════════════════════════════
# Modo laboratorio (aprende sin MFT real)
python3 -m heimdall_timewatch.cli lab
python3 -m heimdall_timewatch.cli lab --html informe_lab.html

# Analizar un MFT real
python3 -m heimdall_timewatch.cli scan -m \$MFT
python3 -m heimdall_timewatch.cli scan -m \$MFT --usn \$J --html out.html
python3 -m heimdall_timewatch.cli scan -m \$MFT --system-install 2024-01-15

# Exportar resultados
python3 -m heimdall_timewatch.cli scan -m \$MFT --json o.json --csv o.csv --html o.html

# Volcar timestamps sin juzgar
python3 -m heimdall_timewatch.cli parse -m \$MFT -o timestamps.csv

═══════════════════════════════════════════════════════════════════
OPCIONES DE SCAN
═══════════════════════════════════════════════════════════════════
-m, --mft           Ruta al fichero $MFT (obligatorio)
--usn               Ruta al $UsnJrnl:$J (corroboración, MUY recomendado)
--system-install    Fecha instalación SO YYYY-MM-DD (mejora H5)
--min-score         Umbral mínimo para reportar (def: 1)
--top N             Mostrar solo los N más sospechosos en consola
--include-dirs      Incluir directorios en el análisis
--only-in-use       Solo archivos en uso (no borrados)
--no-h3             Desactivar H3 (RID, ruidoso)
--json / --csv / --html   Exportar a esos formatos
--no-color          Sin color en consola

═══════════════════════════════════════════════════════════════════
LAS 6 HEURÍSTICAS + USN
═══════════════════════════════════════════════════════════════════
H1   $SI anterior a $FN              Media (Alta si >30 días)
H2   Subsegundos $SI en .0000000     Baja
H3   RID alto + creación antigua     Baja
H4   created > modified              Media
H5   Timestamp futuro/pre-instalación Media
H6   Subsegundos $FN en cero         Media
USN  USN contradice $SI              ALTA (la mejor evidencia)

═══════════════════════════════════════════════════════════════════
NIVELES DE SOSPECHA (por score acumulado)
═══════════════════════════════════════════════════════════════════
Score >= 70   CRÍTICO     ALTA=+50  MEDIA=+25  BAJA=+10
Score >= 45   ALTO
Score >= 20   MEDIO
Score >  0    BAJO
Score == 0    LIMPIO

═══════════════════════════════════════════════════════════════════
EXTRAER ARTEFACTOS
═══════════════════════════════════════════════════════════════════
# FTK Imager: Add Evidence → Logical Drive → exportar $MFT y $Extend\$UsnJrnl
# MFTECmd:    MFTECmd.exe -f C:\$MFT --csv salida
# Linux/TSK:
mmls disco.dd                                    # offset partición
icat -o <offset> disco.dd 0 > \$MFT              # extraer MFT (inode 0)
fls -o <offset> disco.dd -p -r | grep usnjrnl   # localizar $J
icat -o <offset> disco.dd <inode> > \$J          # extraer USN

═══════════════════════════════════════════════════════════════════
TEORÍA CLAVE
═══════════════════════════════════════════════════════════════════
$SI ($STANDARD_INFORMATION) → modificable en user-mode → lo ataca el malware
$FN ($FILE_NAME)            → solo lo escribe el kernel → testigo fiable
8 timestamps por archivo = 4 MACE en $SI + 4 MACE en $FN
FILETIME = 100 ns desde 1601-01-01 UTC
Subsegundos en .0000000 = bandera de herramienta automática
USN Journal = artefacto independiente, la corroboración más potente

═══════════════════════════════════════════════════════════════════
LÍMITE QUE NUNCA DEBES OLVIDAR
═══════════════════════════════════════════════════════════════════
El rename tras timestomping copia $SI→$FN y derrota H1.
Por eso: detección multi-ángulo + USN. Nunca confíes en una sola señal.
Ningún hallazgo es prueba concluyente solo. Corrobora SIEMPRE.
Ausencia de indicadores ≠ ausencia de manipulación.

═══════════════════════════════════════════════════════════════════
MITRE ATT&CK
═══════════════════════════════════════════════════════════════════
T1070.006 — Indicator Removal: Timestomp
Táctica: Defense Evasion
heimdall-timewatch es un control de DETECCIÓN para esta técnica.
```

---

## 📌 Notas Finales

- **El timestomping se basa en que solo ves el `$SI`.** heimdall-timewatch ve también el `$FN` (el testigo del kernel) y el USN Journal (el testigo independiente). Esa es toda la magia.
- **Empieza por el modo `lab`.** Ver los 6 casos plantados detectarse 6/6 te enseña cada heurística mejor que cualquier teoría.
- **La corroboración USN es tu mejor amiga.** Cuando un artefacto independiente confirma la sospecha, pasas de "probable" a "certeza forense". Extrae siempre el `$J` junto al `$MFT`.
- **Sé honesto con los falsos positivos.** Instaladores y ZIPs disparan heurísticas. El timestomping malicioso es puntual, no masivo. Si toda una carpeta dispara lo mismo, sospecha de software legítimo.
- **Ningún hallazgo es prueba concluyente solo.** Es triage e investigación. Corrobora con EDR, logs, PCAP antes de conclusiones formales.
- **Entender la evasión te hace completo.** Saber cómo un atacante derrotaría cada heurística es lo que te convierte en mejor defensor y mejor red teamer a la vez.
- **Cero dependencias es una decisión forense.** Una herramienta auditable y sin supply-chain es una herramienta en la que se puede confiar en un entorno DFIR.

---

> **Plataformas de práctica recomendadas:**
> 1. El modo `lab` integrado (empieza aquí)
> 2. Máquinas Windows de HTB/THM que hayas comprometido (extrae su MFT)
> 3. VMs propias donde practiques timestomping con SetMACE/Timestomp y luego lo detectes
> 4. Imágenes forenses de práctica (DFIR challenges, CTFs forenses)

> **Autor:** heimdall-timewatch y este manual creados por Heindall para el Máster de Ciberseguridad.
> **Basado en:** Brian Carrier "File System Forensic Analysis" + SANS DFIR + inversecos + Magnet Forensics + Microsoft NTFS docs + MITRE ATT&CK
> **Última actualización:** Junio 2026
