# Licencias de terceros

`heimdall-timewatch` se distribuye bajo licencia **MIT** (ver [LICENSE](LICENSE)).

El **motor forense** (`heimdall_timewatch/`) usa exclusivamente la biblioteca
estándar de Python: **no incorpora código de terceros**.

La **GUI opcional** (`gui/`) y el ejecutable empaquetado (`.exe`) sí dependen de
los siguientes componentes de terceros, cada uno bajo su propia licencia:

| Componente | Uso | Licencia | Enlace |
|---|---|---|---|
| **Qt** (vía PySide6) | Framework de la interfaz de escritorio | **LGPL v3** | https://doc.qt.io/qt-6/lgpl.html |
| **PySide6** | Bindings de Qt para Python | **LGPL v3** | https://doc.qt.io/qtforpython-6/licenses.html |
| **keyring** | Almacenamiento seguro de la API key (Windows Credential Manager) | **MIT** | https://github.com/jaraco/keyring/blob/main/LICENSE |
| **PyInstaller** | Empaquetado del ejecutable | **GPL v2 con excepción de bootloader** | https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt |

## Notas de cumplimiento

- **Qt / PySide6 (LGPL v3):** la GUI enlaza Qt de forma **dinámica**. El
  ejecutable se genera en modo *onedir* (PyInstaller), de modo que las
  bibliotecas de Qt quedan como archivos separados en `_internal/` y el usuario
  final puede **reemplazarlas o reenlazarlas**, según exige la LGPL. Al
  distribuir el `.exe` debe incluirse este aviso y el texto de la LGPL v3.
- **PyInstaller:** su *bootloader exception* permite distribuir la aplicación
  empaquetada bajo la licencia que elija el autor (aquí, MIT). PyInstaller no
  impone la GPL al software empaquetado.
- **keyring:** licencia MIT, compatible sin restricciones adicionales.

Este archivo documenta las obligaciones de licencia que aplican **únicamente al
distribuir la GUI o el ejecutable**. El motor y la CLI, al ser solo stdlib,
permanecen libres de dependencias de terceros.
