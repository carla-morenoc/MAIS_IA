# Manual de indexación de videotutoriales de YouTube

Este procedimiento permite indexar vídeos como videotutoriales, conservando los minutos de cada fragmento y el enlace para abrir YouTube en el momento exacto.

## Qué no hay que hacer

No utilizar el botón **Sincronizar** para indexar los vídeos mientras YouTube bloquee la IP del VPS. Ese botón intenta descargar las transcripciones desde el servidor y puede fallar.

El procedimiento correcto es descargar cada transcripción desde el ordenador local y subirla después desde el formulario de la aplicación.

## 1. Descargar la transcripción desde Windows

Abre **Símbolo del sistema** o **PowerShell** en Windows.

La primera vez instala `yt-dlp`:

```cmd
py -m pip install -U yt-dlp
```

Descarga los subtítulos en español sustituyendo la URL por la del vídeo:

```cmd
py -m yt_dlp --skip-download --write-subs --write-auto-subs --sub-langs "es.*,es,en.*" --sub-format vtt -o "%(id)s.%(ext)s" "https://www.youtube.com/watch?v=ID_DEL_VIDEO"
```

Ejemplo:

```cmd
py -m yt_dlp --skip-download --write-subs --write-auto-subs --sub-langs "es.*,es,en.*" --sub-format vtt -o "%(id)s.%(ext)s" "https://www.youtube.com/watch?v=vazaOuqLBLM"
```

El archivo se guarda en la carpeta actual. Si la consola muestra `C:\Users\carla\Desktop\MAIS_IA_copia>`, estará normalmente en:

```text
C:\Users\carla\Desktop\MAIS_IA_copia\ID_DEL_VIDEO.es.vtt
```

Para localizarlo:

```cmd
dir C:\Users\carla\Desktop\MAIS_IA_copia\*.vtt
```

Si aparecen varios archivos, utiliza el que termine en `.es.vtt`.

Los avisos sobre JavaScript o el error 429 del idioma inglés no impiden continuar si se ha creado el archivo `.es.vtt`.

## 2. Subir la transcripción a Maisito

Abre:

```text
https://formacion.mais.es
```

En la columna izquierda, dentro de **Videotutoriales**, localiza **Importar transcripción con tiempos**.

Rellena los campos:

```text
URL del vídeo: URL completa de YouTube
Título: título visible del vídeo
Archivo: archivo .es.vtt descargado
```

Después pulsa **INDEXAR TRANSCRIPCIÓN**.

La aplicación puede mostrar temporalmente:

```text
Indexando...
```

Espera hasta que aparezca:

```text
X chunks
```

Esto significa que la transcripción ha sido indexada correctamente.

## 3. Comprobar que está indexado

También se puede comprobar desde el VPS. Entra por SSH:

```powershell
ssh ubuntu@57.131.148.194
```

Ejecuta esta consulta, cambiando el texto por parte del título:

```bash
curl -s https://formacion.mais.es/api/v1/documents/ | python3 -c "import sys,json; d=json.load(sys.stdin); print([(x['filename'],x['status'],x['total_chunks'],x['error_message']) for x in d if 'Impuesto especial' in x['filename']])"
```

Resultado correcto:

```text
COMPLETED
```

Además, `total_chunks` debe tener un número, no `null`.

## 4. Probar el vídeo

1. En la lista de videotutoriales, espera a que aparezca con `X chunks`.
2. Selecciona el vídeo si aparece como activo.
3. Haz una pregunta concreta sobre su contenido.
4. Pulsa una cita roja de la respuesta.
5. YouTube debe abrirse en el minuto citado.

## 5. Repetir el proceso con otros vídeos

Para cada vídeo:

1. Copiar su URL.
2. Descargar su archivo `.vtt` desde Windows.
3. Introducir URL y título en el formulario.
4. Seleccionar el archivo `.es.vtt`.
5. Pulsar **INDEXAR TRANSCRIPCIÓN**.
6. Esperar a que aparezca `X chunks`.

No es necesario borrar primero los vídeos que aparecen como `PENDING` o `FAILED`. Si se sube una transcripción usando la misma URL, el sistema reutiliza el registro del vídeo y lo vuelve a indexar.

## 6. Errores habituales

### `yt-dlp no se reconoce como comando`

Usar siempre:

```cmd
py -m yt_dlp ...
```

No utilizar directamente `yt-dlp` si la carpeta de scripts de Python no está en el `PATH`.

### No se crea ningún archivo `.vtt`

El vídeo puede no tener subtítulos. Probar otro idioma disponible o elegir otro vídeo.

### El vídeo permanece en `Indexando...`

Comprobar el estado desde el VPS:

```bash
curl -s https://formacion.mais.es/api/v1/documents/ | python3 -c "import sys,json; d=json.load(sys.stdin); print([(x['filename'],x['status'],x['error_message']) for x in d if x['document_type']=='youtube'])"
```

Si el estado es `COMPLETED`, recargar la web con `Ctrl + F5`.

Si el estado es `FAILED`, revisar `error_message`.

### Aparece `YouTube is blocking requests from your IP`

Ese error corresponde al método antiguo que descargaba desde el VPS. No pulsar **Sincronizar** y utilizar el procedimiento manual de este documento.

### El estado es `PENDING` y no cambia

Comprobar que el worker está iniciado:

```bash
sudo docker compose -f /home/ubuntu/docker-compose.prod.yml ps celery_worker
```

Si está detenido:

```bash
sudo docker compose -f /home/ubuntu/docker-compose.prod.yml start celery_worker
```

Después volver a subir la transcripción desde el formulario.

## 7. Mantenimiento del sistema

Para ver los logs del worker:

```bash
sudo docker compose -f /home/ubuntu/docker-compose.prod.yml logs -f --tail=50 celery_worker
```

Para salir de los logs sin detener el worker:

```text
Ctrl+C
```

Para detener el worker, sin borrar datos:

```bash
sudo docker compose -f /home/ubuntu/docker-compose.prod.yml stop celery_worker
```

La IA seguirá funcionando con los vídeos que ya tengan vectores indexados, aunque el worker esté detenido.

## Resumen rápido

```text
Windows: descargar .vtt con py -m yt_dlp
Web: introducir URL + título + archivo .vtt
Web: pulsar INDEXAR TRANSCRIPCIÓN
Esperar: X chunks
Probar: cita roja -> YouTube en el minuto correspondiente
```
