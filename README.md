# 🖼️ Background Remover (Fondo Blanco Inteligente)

Sistema automatizado y modular en Python para la eliminación de fondos en imágenes y su sustitución automática por un **fondo blanco puro (`#FFFFFF`)** de alta calidad (o cualquier color/transparencia personalizada).

Diseñado con una arquitectura desacoplada de nivel empresarial, soporte para procesamiento por lotes con multihilo, monitoreo de carpetas en tiempo real (*hot-folder*), resiliencia con *Circuit Breaker* y registro de auditoría/métricas.

---

## 📑 Tabla de Contenidos
- [Características Principales](#-características-principales)
- [Estructura del Proyecto](#-estructura-del-proyecto)
- [Instalación y Requisitos](#-instalación-y-requisitos)
- [Configuración (.env)](#-configuración-env)
- [Guía de Uso y Comandos](#-guía-de-uso-y-comandos)
  - [1. Procesamiento de Imagen Individual](#1-procesamiento-de-imagen-individual)
  - [2. Procesamiento por Lotes (Batch Concurrente)](#2-procesamiento-por-lotes-batch-concurrente)
  - [3. Modo Vigilante en Tiempo Real (Hot-Folder Watcher)](#3-modo-vigilante-en-tiempo-real-hot-folder-watcher)
  - [4. Consulta de Métricas y Estadísticas](#4-consulta-de-métricas-y-estadísticas)
- [Opciones Avanzadas](#-opciones-avanzadas)
- [Manejo de Errores y Resiliencia](#-manejo-de-errores-y-resiliencia)
- [Ejecución de Pruebas](#-ejecución-de-pruebas)

---

## ✨ Características Principales

- 🤖 **Motor IA Optimizado (`rembg` + `onnxruntime`)**: Sesión del modelo precargada en memoria para evitar sobrecostos por imagen.
- 🎨 **Composición a Fondo Blanco Puro**: Fusión precisa con canal alfa hacia `RGB(255, 255, 255)` sin artefactos oscuros en los bordes.
- 🧵 **Procesamiento Multihilo**: Ejecución paralela en lotes con barra de progreso dinámica (`tqdm`).
- 👁️ **Hot-Folder Watcher**: Monitorea `input/` en tiempo real; cualquier imagen nueva es procesada a `output/` y archivada en `input/processed/`.
- 🛡️ **Patrón Circuit Breaker & Retry**: Protege la ejecución contra fallos consecutivos de I/O o memoria.
- 📊 **Seguimiento Persistente**: Métricas de tiempo, dimensiones y resolución registradas de forma limpia en `%APPDATA%\BackgroundRemover\processing_tracker.json`.
- 📝 **Logging Rotativo**: Salida en consola y archivo rotativo de 10 MB (`%APPDATA%\BackgroundRemover\logs\remover_app.log`).
- 🧹 **Ejecución Limpia (Zero Pollution)**: Al ejecutar el `.exe`, no se generan carpetas temporales ni archivos no deseados en la ubicación del programa; todo el almacenamiento interno se aísla en `AppData`.

---

## 📁 Estructura del Proyecto

```
background_remover/
├── main.py                                  # Punto de entrada principal (GUI / CLI)
├── .env.example                             # Plantilla de configuración
├── .env                                     # Configuración activa
├── requirements.txt                         # Dependencias del sistema
├── README.md                                # Documentación principal
│
├── modules/
│   ├── core/
│   │   ├── __init__.py
│   │   └── app.py                           # Orquestación de CLI, logging rotativo y despacho
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── config.py                        # Dataclasses de configuración tipadas
│   │   ├── error_codes.py                   # Catálogo de códigos de error estructurados (ERR_XXXX)
│   │   └── settings_manager.py              # Persistencia de preferencias en AppData
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── bg_remover_service.py            # Gestión de sesiones Rembg ONNX y CircuitBreaker
│   │   ├── image_processor.py               # Composición con Pillow (fondo blanco, márgenes, formatos)
│   │   ├── batch_service.py                 # Procesamiento concurrente por lotes
│   │   ├── folder_watcher.py                # Servicio de monitoreo en tiempo real (watchdog)
│   │   ├── file_manager.py                  # Detección de formatos válidos, rutas y archivado
│   │   └── tracker_service.py               # Persistencia de métricas y estadísticas
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   └── app_gui.py                       # Interfaz gráfica interactiva y moderna con Flet
│   │
│   └── utils/
│       ├── __init__.py
│       └── helpers.py                       # Parsers de color (HEX/RGB), CircuitBreaker y retry
│
├── assets/                                  # Iconos y recursos visuales (.ico, .png, splash)
├── docs/
│   ├── CODIGOS_ERROR.md                     # Catálogo exhaustivo de errores y soluciones
│   └── MANUAL_USO.md                        # Guía de usuario y parámetros detallados
│
└── tests/
    └── test_remover.py                      # Suite de pruebas unitarias y de integración
```

> **Nota sobre almacenamiento interno**: Los logs (`logs/`), el tracker (`processing_tracker.json`) y las preferencias (`settings.json`) se guardan de forma aislada en `%APPDATA%\BackgroundRemover\` para evitar crear archivos o carpetas innecesarias en el directorio del ejecutable. Las carpetas de salida (`output/`) se crean únicamente bajo demanda al procesar imágenes.

---

## 🛠️ Instalación y Requisitos

1. Clonar o ubicarse en el directorio del proyecto:
   ```bash
   cd background_remover
   ```
2. Instalar las dependencias requeridas:
   ```bash
   pip install -r requirements.txt
   ```
3. Copiar la configuración base:
   ```bash
   cp .env.example .env
   ```

---

## ⚙️ Configuración (.env)

El archivo `.env` permite personalizar el comportamiento general:

```ini
# Directorios
INPUT_DIR=input
OUTPUT_DIR=output
LOGS_DIR=logs

# Configuración de Fondo
# Opciones: 255,255,255 (Blanco), white, #FFFFFF, transparent
BG_COLOR=255,255,255

# Formato y Calidad de Salida (JPEG, PNG, WEBP)
OUTPUT_FORMAT=JPEG
OUTPUT_QUALITY=95

# Motor de IA Rembg (u2net, u2netp, isnet-general-use)
DEFAULT_MODEL=u2net
ALPHA_MATTING=false

# Ajustes Geométricos
AUTO_CROP=false
PADDING_PERCENT=5

# Procesamiento por Lotes y Rendimiento
BATCH_LIMIT=20
MAX_BATCH_LIMIT=20
MAX_WORKERS=4
TIMEOUT_SECONDS=60
MAX_FILE_SIZE_MB=50
```

> [!WARNING]
> **Aviso de Rendimiento y Estabilidad:** Entre mayor sea la cantidad de imágenes cargadas en un mismo lote, mayor es el consumo de memoria RAM y la probabilidad de errores o bloqueos del sistema. Por este motivo, se establece un **límite recomendado de 20 imágenes por lote**.

---

## 🚀 Guía de Uso y Comandos

### 🖥️ 1. Modo Interfaz Gráfica (GUI Interactiva)
Inicia la aplicación de escritorio visual con selectores de archivos, carpetas, vista previa de color y configuración de límites:
```bash
python main.py --gui
```
*(También puedes usar el atajo corto: `python main.py -g`)*

Permite:
- Alternar entre **Imagen Individual** o **Carpeta con Imágenes (Lote)**.
- Seleccionar imagen/carpeta de origen y carpeta de destino con botones de explorador nativo.
- Configurar el **Límite de imágenes por lote** (por defecto 20).
- Escoger color de fondo (Blanco `#FFFFFF`, Transparente o Paleta de Colores).
- Seleccionar formato de salida (`JPEG`, `PNG`, `WEBP`).
- Ver barra de progreso en tiempo real y abrir directamente la carpeta de resultados.

### 2. Procesamiento de Imagen Individual (CLI)
Convierte una imagen específica por comando:
```bash
python main.py -i ruta/a/tu_imagen.jpg -o ruta/a/resultado.jpg
```

### 3. Procesamiento por Lotes (Batch Concurrente con Límite)
Procesa imágenes de una carpeta en paralelo respetando el límite establecido:
```bash
# Procesa la carpeta input/ con el límite por defecto (20 imágenes):
python main.py

# O especificando carpetas, límite personalizado e hilos:
python main.py -i mis_fotos/ -o fotos_blancas/ --limit 20 --workers 4
```

### 4. Modo Vigilante en Tiempo Real (Hot-Folder Watcher)
Monitorea continuamente la carpeta `input/`. Cada vez que agregues una imagen, se procesará automáticamente y se guardará en `output/`:
```bash
python main.py --watch
```

### 5. Consulta de Métricas y Estadísticas
Visualiza el resumen histórico de procesamiento (imágenes procesadas, éxitos, fallos y tiempos acumulados):
```bash
python main.py --stats
```

---

## 🎨 Opciones Avanzadas

| Parámetro | Descripción | Ejemplo |
| :--- | :--- | :--- |
| `-c, --color` | Cambia el color de fondo (Nombre, Hex o RGB). | `-c "#F5F5F5"` o `-c transparent` |
| `-l, --limit` | Límite de imágenes por lote (por defecto 20). | `-l 20` |
| `-f, --format` | Define el formato de salida (`JPEG`, `PNG`, `WEBP`). | `-f WEBP` |
| `-m, --model` | Selecciona el modelo IA (`u2net`, `isnet-general-use`). | `-m isnet-general-use` |
| `--auto-crop` | Recorta los bordes vacíos y añade un margen proporcional. | `--auto-crop` |
| `--alpha-matting` | Activa refinamiento de bordes para cabello o transparencias. | `--alpha-matting` |
| `-r, --recursive`| Procesa imágenes en subcarpetas recursivamente. | `-r` |
| `--workers` | Número de hilos simultáneos para el procesamiento por lotes. | `--workers 8` |

---

## 🛡️ Manejo de Errores y Resiliencia

El sistema cuenta con un catálogo formal de códigos de error estructurados:
- **`ERR_1001 - ERR_1099`**: Errores de configuración y argumentos.
- **`ERR_1101 - ERR_1199`**: Errores de archivo, formato e I/O.
- **`ERR_1201 - ERR_1299`**: Errores del motor IA y composición con Pillow.
- **`ERR_1301 - ERR_1399`**: Errores del observador de carpetas y concurrencia.

Para más detalles, consulta [`docs/CODIGOS_ERROR.md`](docs/CODIGOS_ERROR.md).

---

## 🧪 Ejecución de Pruebas

Para ejecutar la suite completa de pruebas unitarias y de integración:
```bash
python -m unittest discover tests
```

---

## 📦 Compilación a Ejecutable (.exe)

Para generar un ejecutable independiente de Windows que empaquete la interfaz gráfica y todas sus dependencias sin necesidad de tener Python instalado:

1. **Instalar PyInstaller**:
   ```bash
   pip install pyinstaller
   ```

2. **Compilar la Aplicación**:
   ```bash
   python -m PyInstaller --noconsole --onefile --splash "assets/splash.png" --collect-all flet --copy-metadata pymatting --copy-metadata rembg --add-data "assets;assets" --icon="assets/app_icon.ico" --name "BackgroundRemover" main.py
   ```
   > `--splash` muestra la imagen durante la extracción del `.exe` (fase de mayor espera).
   > `assets/splash.png` se incluye automáticamente vía `--add-data "assets;assets"`.

> **Nota de Aislamiento y Persistencia**: Todas las preferencias del usuario (rutas, color, formato, modelo de IA seleccionado), los registros de ejecución (`logs/`) y el historial de rendimiento (`processing_tracker.json`) se almacenan de manera automática e invisible en `%APPDATA%\BackgroundRemover\`. Al ejecutar el `.exe`, la carpeta de trabajo se mantiene 100% limpia sin crear carpetas auxiliares innecesarias.
