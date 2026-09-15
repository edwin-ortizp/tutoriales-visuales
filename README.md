# Tutoriales Visuales 0.6 — editor local

Aplicación de escritorio para Windows que crea tutoriales paso a paso a partir de capturas. Todo permanece en el equipo: no hay servidor, cuentas, telemetría, IA, OCR ni registro de teclado.

## Repositorio de desarrollo

La ubicación principal para desarrollo es `C:\laragon\www\tutoriales-visuales`. El repositorio contiene únicamente código fuente, pruebas, recursos y archivos necesarios para construir la aplicación.

Los proyectos `.tutorial`, HTML exportados, entornos virtuales, compilaciones e instaladores no deben añadirse a Git. Pueden contener capturas o información sensible y se generan localmente. En futuras publicaciones, los instaladores y ZIP portables deben adjuntarse a una GitHub Release en lugar de guardarse en el historial del repositorio.

## Funciones principales

- Captura de la ventana activa mediante `Ctrl+Shift+F9`.
- Captura con temporizador de tres segundos e importación de PNG, JPEG o WebP.
- Títulos, instrucciones y orden editable de los pasos.
- Recorte no destructivo y zoom de 1× a 3× con centro independiente.
- Marcadores, flechas y rectángulos con selección, movimiento y redimensionamiento.
- Ocultamiento sólido seguro y desenfoque visual para información sensible.
- Deshacer y rehacer cambios visuales con `Ctrl+Z` y `Ctrl+Y`.
- Identidad por tutorial: nombre de plataforma, logo y color principal.
- Vista previa completa en el navegador y opción **Exportar y abrir**.
- Guardado y reapertura de proyectos `.tutorial`.
- Recuperación automática cada diez segundos ante cierres inesperados.
- Negritas y enlaces seguros en la descripción y las instrucciones.
- Portada editorial con total de pasos, duración estimada e inicio claro del tutorial.
- Índice desplegable, navegación lateral en escritorio y barra inferior en móvil.
- Progreso durante el desplazamiento y cierre explícito del tutorial.
- Exportación de un único HTML responsivo, imprimible y completamente offline.

La captura original se conserva dentro del `.tutorial`. Los ocultamientos, el recorte, el zoom y las anotaciones solo se aplican a la imagen procesada que se incrusta en el HTML.

## Skill de Codex para borradores asistidos

La skill versionada en `skills\crear-tutorial-visual` ayuda a convertir capturas ordenadas en un `.tutorial` editable y a revisar los textos de proyectos existentes. La IA muestra primero un borrador, aclara lo que no puede comprobar y solo ejecuta el generador después de una aprobación explícita.

Instálala o actualízala en la carpeta personal de Codex desde PowerShell:

```powershell
.\scripts\install-codex-skill.ps1
```

Después puede invocarse como `$crear-tutorial-visual`. El generador determinista también está disponible directamente:

```powershell
python scripts\ai_tutorial.py create --images .\capturas --draft .\borrador.json --output .\mi-guia.tutorial
python scripts\ai_tutorial.py inspect --project .\mi-guia.tutorial --output .\borrador.json
python scripts\ai_tutorial.py update --project .\mi-guia.tutorial --draft .\borrador.json
```

Los comandos `create` y `update` rechazan borradores no aprobados, dudas pendientes, enlaces inseguros, imágenes dañadas o duplicadas y cambios de IDs. Los proyectos creados quedan pendientes de revisión visual.

## Instalación para usuarios finales

- Requiere Windows 10 u 11 de 64 bits.
- Ejecuta `Tutoriales-Visuales-Setup-0.6.0.exe` y sigue el asistente en español.
- No requiere Python, permisos de administrador ni conexión a Internet.
- La instalación crea accesos directos en el menú Inicio y el escritorio y asocia los archivos `.tutorial`.
- Al abrir un segundo proyecto, la aplicación activa la ventana existente en lugar de iniciar otra copia.

El programa se instala para el usuario actual en `%LOCALAPPDATA%\Programs\Tutoriales Visuales`. Como el instalador no tiene firma comercial, Windows SmartScreen puede mostrar una advertencia; verifica previamente el SHA-256 incluido en la entrega.

El ZIP portable se conserva para diagnóstico técnico. Para usarlo, descomprime todos sus archivos antes de ejecutar `TutorialesVisuales.exe`.

## Ejecución desde el código fuente

Para desarrollo se requiere Python 3.10 o posterior. Desde PowerShell, dentro de `C:\laragon\www\tutoriales-visuales`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python run.py
```

Invocaciones públicas del ejecutable:

```text
TutorialesVisuales.exe
TutorialesVisuales.exe archivo.tutorial
TutorialesVisuales.exe --version
TutorialesVisuales.exe --smoke-test
```

## Flujo recomendado

1. Escribe el título, la descripción y, opcionalmente, la identidad de la plataforma.
2. Abre la aplicación o navegador que quieres documentar y presiona `Ctrl+Shift+F9`.
3. Escribe la instrucción del paso.
   - Selecciona texto y usa **Negrita** o **Enlace…** cuando necesites destacarlo.
   - Los enlaces admiten direcciones web `http/https` y correo `mailto`.
4. Revisa la captura con estas herramientas:
   - **Seleccionar:** mueve, redimensiona o elimina anotaciones.
   - **Recortar:** arrastra el área que debe conservarse.
   - **Centro zoom:** elige el área alrededor de la cual se aplicará el zoom.
   - **Marcador:** señala un punto concreto.
   - **Flecha/Rectángulo:** destaca una acción o región.
   - **Ocultar:** sustituye los datos con un bloque oscuro; es la opción segura.
   - **Desenfocar:** oculta visualmente con desenfoque, pero es menos seguro.
5. Comprueba el resultado en **Vista final del paso** y marca la revisión visual como completada.
6. Usa `F5` para abrir la vista previa completa.
7. Guarda el `.tutorial` y exporta el HTML.

Antes de exportar, la aplicación advierte sobre instrucciones vacías, pasos sin revisión visual y anotaciones que quedarían fuera del recorte o zoom.

## Formato `.tutorial`

La versión 0.6 mantiene el esquema 3: además de imágenes originales, recorte, zoom, anotaciones e identidad, guarda el texto y sus marcas de negrita o enlace de forma estructurada. Los proyectos de esquemas 1 y 2 se migran automáticamente; el esquema 1 conserva el antiguo marcador como una anotación explícita. Los proyectos guardados con 0.6 siguen siendo compatibles con las aplicaciones 0.4 y 0.5.

El archivo es un ZIP portable con `project.json`, capturas PNG y logo opcional. El HTML exportado contiene las imágenes finales, identidad, estilos y navegación embebidos; no incluye rutas locales ni recursos externos automáticos. La portada calcula la duración como 15 segundos por paso, redondeada hacia arriba. Un script local, sin llamadas de red ni almacenamiento, actualiza el paso, porcentaje y navegación según el desplazamiento. Los enlaces solo se abren cuando el lector los pulsa.

Mientras hay cambios pendientes, la aplicación mantiene una sola copia temporal en `%LOCALAPPDATA%\Tutoriales Visuales\recovery`. Al iniciar después de un cierre inesperado permite recuperarla o descartarla. La copia se elimina después de guardar, descartar o cerrar limpiamente.

## Construcción de una versión

En Windows x64, el comando único de publicación es:

```powershell
.\scripts\build-release.ps1
```

Si Inno Setup 6 no está instalado y `winget` está disponible:

```powershell
.\scripts\build-release.ps1 -BootstrapTools
```

El proceso crea un entorno virtual limpio, instala dependencias fijadas, ejecuta las pruebas, genera el paquete `onedir`, valida el ejecutable con `--smoke-test`, compila el instalador y produce en `release\`:

- `Tutoriales-Visuales-Setup-0.6.0.exe`
- `Tutoriales-Visuales-Portable-0.6.0.zip`
- `Tutoriales-Visuales-0.6.0.sha256`
- `release-manifest.json`

La única fuente de versión es `tutorial_app.__version__`; al cambiarla, los nombres, metadatos del ejecutable, instalador y manifiesto se actualizan juntos.

La construcción debe ejecutarse desde la raíz del repositorio. El script resuelve `assets`, `packaging`, `build`, `dist` y `release` de forma relativa a esa raíz; estos tres últimos directorios permanecen fuera de Git.

## Pruebas

```powershell
python -m pytest -q
```

La suite cubre migraciones de esquemas 1 y 2, recuperación atómica, texto enriquecido seguro, portada editorial, estimación de tiempo, navegación responsive y progreso del HTML, persistencia exacta de capturas, recorte y zoom, privacidad, anotaciones, deshacer/rehacer, caracteres españoles, identidad y ausencia de recursos externos automáticos.

## Límites actuales

- No identifica botones ni clics automáticamente.
- No captura pulsaciones de teclado.
- No incluye texto libre sobre la imagen ni dibujo a mano.
- No permite estilos distintos por anotación.
- No publica tutoriales ni incluye actualizaciones automáticas.
- No incluye historial de versiones, duplicación o arrastre de pasos.

El desenfoque es una ayuda visual, no una garantía de anonimización. Para contraseñas, documentos, correos u otros datos sensibles utiliza siempre **Ocultar**.
