# Catálogo de Códigos de Error - Background Remover

## Descripción General
Este documento contiene la lista completa de códigos de error estructurados del sistema Background Remover. Cada error incluye su código único `ERR_XXXX`, nivel de severidad, descripción técnica y acción correctiva recomendada.

---

## Estructura de Códigos
- **1000-1099**: Errores de Configuración y Parámetros
- **1100-1199**: Errores de Archivo, Formato e I/O
- **1200-1299**: Errores del Motor IA (Rembg / ONNX) y Composición
- **1300-1399**: Errores del Vigilante de Carpetas y Concurrencia
- **1900-1999**: Errores de Sistema y Excepciones No Controladas

---

## Códigos de Error

### 1. Configuración (1000-1099)
| Código | Severidad | Descripción | Acción Recomendada |
| :--- | :--- | :--- | :--- |
| `ERR_1001` | HIGH | Formato de color inválido en `BG_COLOR` o `--color`. | Use `'white'`, `'#FFFFFF'` o `'255,255,255'`. |
| `ERR_1002` | HIGH | Modelo IA no reconocido. | Utilice `u2net`, `u2netp` o `isnet-general-use`. |
| `ERR_1003` | MEDIUM | Formato de salida no soportado. | Configure `JPEG`, `PNG` o `WEBP`. |
| `ERR_1004` | HIGH | Directorio de entrada/salida inaccesible. | Verifique la existencia y permisos de las carpetas. |

### 2. Archivos e I/O (1100-1199)
| Código | Severidad | Descripción | Acción Recomendada |
| :--- | :--- | :--- | :--- |
| `ERR_1101` | HIGH | Archivo de entrada no encontrado. | Revise la ruta del archivo provisto en `--input`. |
| `ERR_1102` | HIGH | Archivo corrupto o no es imagen válida. | Verifique que el archivo sea una imagen válida legible por Pillow. |
| `ERR_1103` | MEDIUM | El archivo supera el tamaño máximo permitido. | Reduzca la resolución o aumente `MAX_FILE_SIZE_MB`. |
| `ERR_1104` | HIGH | Permiso denegado al leer o guardar imagen. | Verifique permisos de escritura en la carpeta de salida. |
| `ERR_1105` | HIGH | Fallo al guardar la imagen procesada en disco. | Compruebe espacio en disco o nombres de archivo válidos. |

### 3. Motor IA y Composición (1200-1299)
| Código | Severidad | Descripción | Acción Recomendada |
| :--- | :--- | :--- | :--- |
| `ERR_1201` | CRITICAL | Fallo al cargar pesos ONNX del modelo. | Compruebe la conexión a internet para la descarga inicial de `u2net.onnx`. |
| `ERR_1202` | HIGH | Fallo durante la inferencia de recorte. | Revise el log de errores para analizar el error de sesión ONNX. |
| `ERR_1203` | MEDIUM | Tiempo de inferencia excedido (`TIMEOUT_SECONDS`). | Incremente el tiempo límite para imágenes de muy alta resolución. |
| `ERR_1204` | HIGH | Fallo en la fusión sobre fondo blanco. | Compruebe compatibilidad de modos de imagen (RGBA a RGB). |
| `ERR_1205` | LOW | Error en el refinamiento *Alpha Matting*. | Desactive `--alpha-matting` o ajuste los umbrales de borde. |

### 4. Vigilante y Concurrencia (1300-1399)
| Código | Severidad | Descripción | Acción Recomendada |
| :--- | :--- | :--- | :--- |
| `ERR_1301` | HIGH | Fallo al iniciar el observador de carpetas (*watchdog*). | Compruebe que la carpeta `input/` exista y sea observable. |
| `ERR_1302` | MEDIUM | Fallo al procesar un evento de archivo entrante. | Verifique que el archivo no esté bloqueado por otro proceso. |
| `ERR_1303` | MEDIUM | Uno de los hilos de procesamiento en lote tardó demasiado. | Reduzca `--workers` si el equipo tiene CPU limitada. |

### 5. Generales (1900-1999)
| Código | Severidad | Descripción | Acción Recomendada |
| :--- | :--- | :--- | :--- |
| `ERR_1901` | CRITICAL | Memoria RAM insuficiente. | Procese las imágenes en lotes más pequeños. |
| `ERR_1999` | HIGH | Error inesperado no catalogado. | Revise el archivo `logs/remover_app.log` con el stacktrace completo. |
