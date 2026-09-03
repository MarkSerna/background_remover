# Manual de Uso - Background Remover (Fondo Blanco)

## 🚀 Introducción
**Background Remover** es una herramienta automatizada y modular en Python diseñada para eliminar el fondo de cualquier imagen y sustituirlo automáticamente por un fondo **blanco puro (`#FFFFFF`)** de alta calidad (o cualquier color/transparencia deseada).

---

## 🛠️ Instalación y Requisitos

1. Asegúrate de tener Python 3.9+ instalado.
2. Instala las dependencias necesarias:
   ```bash
   pip install -r requirements.txt
   ```
3. (Opcional) Ajusta las variables del archivo `.env` según tus necesidades.

---

## 💻 Modos de Uso

### 0. Modo Interfaz Gráfica (Recomendado) 🖥️
Abre la ventana visual interactiva para seleccionar archivos/carpetas y opciones de forma gráfica:
```bash
python main.py --gui
# o con atajo corto:
python main.py -g
```

### 1. Procesar una Imagen Individual (Línea de Comandos)
Convierte una imagen específica y genera el resultado con fondo blanco:
```bash
python main.py -i ruta/a/tu_foto.jpg -o ruta/a/resultado.jpg
```

### 2. Procesar una Carpeta Completa (Batch / Por Lotes)
Procesa todas las imágenes contenidas en una carpeta en paralelo respetando el límite:
```bash
python main.py -i input/ -o output/ --limit 20 --workers 4
```
*Si no especificas `-i`, por defecto procesará las imágenes en la carpeta `input/` aplicando el límite de 20 imágenes.*

> ⚠️ **Nota de Rendimiento:** Entre mayor sea el número de imágenes en el lote, mayor es el consumo de memoria y la probabilidad de errores. Se recomienda mantener lotes de hasta 20 imágenes.

### 3. Modo Vigilante en Tiempo Real (Hot-Folder Watcher) 👁️
Monitorea la carpeta `input/` de forma continua. Cada vez que pegues o descargues una imagen allí, se procesará automáticamente y se guardará en `output/`:
```bash
python main.py --watch
```

---

## 🎨 Opciones Avanzadas

| Parámetro | Descripción | Ejemplo |
| :--- | :--- | :--- |
| `-c, --color` | Define un color de fondo personalizado (Hex, RGB o nombre). | `-c "#FFFFFF"` o `-c transparent` |
| `-l, --limit` | Límite de imágenes por lote (por defecto 20). | `-l 20` |
| `-f, --format` | Formato de la imagen de salida (`JPEG`, `PNG`, `WEBP`). | `-f WEBP` |
| `-m, --model` | Modelo de IA a utilizar (`u2net`, `isnet-general-use`, etc.). | `-m isnet-general-use` |
| `--auto-crop` | Recorta los bordes vacíos y centra el sujeto con margen proporcional. | `--auto-crop` |
| `--alpha-matting` | Activa refinamiento de bordes para cabello, pelaje o bordes suaves. | `--alpha-matting` |
| `--stats` | Muestra el resumen histórico de imágenes procesadas y métricas. | `python main.py --stats` |

---

## 📁 Estructura de Directorios y Almacenamiento
 
- `output/`: Carpeta donde se generan las imágenes procesadas (creada bajo demanda).
- `%APPDATA%\BackgroundRemover\`:
  - `settings.json`: Preferencias persistentes del usuario entre sesiones.
  - `logs/remover_app.log`: Registros de ejecución y auditoría.
  - `processing_tracker.json`: Registro histórico de métricas y rendimiento.

---

## 📦 Generación del Ejecutable (.exe)

Para crear el archivo ejecutable de Windows standalone:

```bash
pip install pyinstaller
python -m PyInstaller --noconsole --onefile --collect-all flet --copy-metadata pymatting --copy-metadata rembg --add-data "assets;assets" --icon="assets/app_icon.ico" --name "BackgroundRemover" main.py
```

El ejecutable estará disponible en `dist/BackgroundRemover.exe`.
