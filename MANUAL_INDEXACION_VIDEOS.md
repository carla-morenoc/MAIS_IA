# Guia sencilla para indexar videotutoriales

Este manual explica como descargar la transcripcion de un video de YouTube desde Windows, subirla a Maisito y comprobar que ha terminado correctamente.

El proceso se hace **un video cada vez** para poder revisar facilmente el resultado.

## Como funciona

1. Windows descarga la transcripcion del video en un archivo `.vtt`.
2. Se sube ese archivo desde el panel de Maisito.
3. Maisito lo divide en fragmentos de unos 30 segundos llamados `chunks`.
4. Los fragmentos se guardan en la base de datos vectorial.
5. El chat puede usar el contenido y abrir YouTube en el segundo exacto de cada cita.

La descarga se hace desde tu ordenador porque YouTube puede bloquear la IP de la VPS.

## 1. Descargar el VTT desde Windows

### Instalar yt-dlp

Solo hay que hacerlo la primera vez. Abre **CMD** o PowerShell y ejecuta:

```cmd
py -m pip install -U yt-dlp
```

### Descargar un video

Puedes crear una carpeta para guardar las transcripciones:

```cmd
mkdir vtt_videos
cd vtt_videos
```

En **CMD**, ejecuta todo el comando en una sola linea. Cambia la URL por la del video. Este comando descarga solo ese video:

```cmd
py -m yt_dlp --no-playlist --skip-download --write-subs --write-auto-subs --sub-langs "es.*,es,en.*" --sub-format vtt --ignore-errors -o "%(id)s.%(ext)s" "https://www.youtube.com/watch?v=ID_DEL_VIDEO"
```

Ejemplo:

```cmd
py -m yt_dlp --no-playlist --skip-download --write-subs --write-auto-subs --sub-langs "es.*,es,en.*" --sub-format vtt --ignore-errors -o "%(id)s.%(ext)s" "https://www.youtube.com/watch?v=vazaOuqLBLM"
```

En **PowerShell**, puedes usar el mismo comando. Si lo escribes en varias lineas, usa el caracter de continuacion `` ` ``. No uses `` ` `` en CMD.

El archivo tendra normalmente un nombre parecido a:

```text
vazaOuqLBLM.es.vtt
```

Comprueba que se ha creado:

```cmd
dir *.vtt
```

Si hay varios idiomas, utiliza el archivo que termine en `.es.vtt`.

### Avisos normales de yt-dlp

Estos avisos no son un problema si se crea el archivo `.vtt`:

* Avisos sobre JavaScript o `EJS`.
* Avisos sobre `impersonation`.
* Error 429 para un idioma alternativo, si se ha descargado el `.es.vtt`.

Si termina con `Finished downloading` y existe el archivo `.vtt`, puedes continuar.

## 2. Subir un video a Maisito

1. Abre [https://formacion.mais.es](https://formacion.mais.es).
2. En la columna izquierda, localiza **Videotutoriales**.
3. Busca el bloque **Importar transcripcion con tiempos**.
4. Completa los campos:

	* **URL del video de YouTube**: URL completa del video.
	* **Titulo del video**: titulo que quieres ver en la lista.
	* **Archivo**: el archivo `.es.vtt` descargado.

5. Pulsa **Indexar transcripcion**.

No pulses **Sincronizar** para este procedimiento. Ese boton intenta descargar la transcripcion desde la VPS y YouTube puede bloquearla.

## 3. Entender los estados

En la lista de videotutoriales veras estos estados:

| Estado | Significado | Que hacer |
|---|---|---|
| `PENDING` | La transcripcion esta en la cola de Celery. | Esperar unos segundos y revisar. |
| `PROCESSING` | El worker esta creando embeddings y guardando los chunks. | Esperar y consultar los logs si tarda demasiado. |
| `COMPLETED` | La indexacion ha terminado correctamente. | Debe aparecer el numero de chunks. Probar una pregunta. |
| `FAILED` | Ha ocurrido un error durante la indexacion. | Revisar el mensaje y los logs del worker. |

En la web, `PENDING` y `PROCESSING` aparecen como **Indexando...**. Cuando termina, aparece algo parecido a `25 chunks`.

Un video esta listo cuando:

* aparece `COMPLETED`;
* muestra un numero de chunks;
* se puede seleccionar en la lista;
* una pregunta sobre su contenido devuelve una cita roja con el minuto del video.

## 4. Ver los logs del procesamiento

Conectate a la VPS por SSH:

```bash
ssh ubuntu@57.131.148.194
```

Entra en la carpeta del proyecto:

```bash
cd /home/ubuntu/opt/maisito
```

### Ver los logs en directo

Este es el comando principal mientras subes un `.vtt`:

```bash
sudo docker compose -f docker-compose.prod.yml logs -f --tail=50 celery_worker
```

Para salir de los logs sin detener nada, pulsa `Ctrl+C`.

### Ver solo los ultimos minutos

```bash
sudo docker compose -f docker-compose.prod.yml logs --since=10m celery_worker
```

### Comprobar que el worker esta encendido

```bash
sudo docker compose -f docker-compose.prod.yml ps celery_worker
```

Debe aparecer con estado `Up` o `running`.

## 5. Comprobar el estado desde la VPS

Para listar los videotutoriales y su estado:

```bash
curl -s https://formacion.mais.es/api/v1/documents/ | python3 -c "import sys,json; d=json.load(sys.stdin); print([(x['filename'],x['status'],x['total_chunks'],x['error_message']) for x in d if x.get('document_type') == 'youtube'])"
```

Para buscar un video concreto, cambia `TEXTO_DEL_TITULO`:

```bash
curl -s https://formacion.mais.es/api/v1/documents/ | python3 -c "import sys,json; d=json.load(sys.stdin); print([(x['filename'],x['status'],x['total_chunks'],x['error_message']) for x in d if 'TEXTO_DEL_TITULO'.lower() in x['filename'].lower()])"
```

Resultado correcto de ejemplo:

```text
('Como hacer una factura', 'COMPLETED', 18, None)
```

`total_chunks` debe tener un numero. Si aparece `null`, la indexacion aun no ha terminado o ha fallado.

## 6. Que hacer si no termina

### Se queda en `PENDING`

Comprueba el worker:

```bash
sudo docker compose -f docker-compose.prod.yml ps celery_worker
```

Si esta detenido, inicialo:

```bash
sudo docker compose -f docker-compose.prod.yml start celery_worker
```

Despues vuelve a subir el `.vtt` desde el formulario.

### Se queda en `PROCESSING`

Mira los ultimos logs:

```bash
sudo docker compose -f docker-compose.prod.yml logs --tail=100 celery_worker
```

Si el worker sigue funcionando, espera. La creacion de embeddings puede tardar dependiendo de la longitud del video.

### Aparece `FAILED`

1. Ejecuta:

	```bash
	sudo docker compose -f docker-compose.prod.yml logs --tail=100 celery_worker
	```

2. Consulta el estado para leer `error_message`.
3. Corrige el problema indicado.
4. Vuelve a subir el mismo `.vtt` con la misma URL.

Si usas la misma URL, Maisito reutiliza el registro del video y lo vuelve a indexar.

### Error de YouTube o IP bloqueada

No uses **Sincronizar**. Descarga el `.vtt` en Windows con `yt-dlp` y utiliza **Importar transcripcion con tiempos**.

### El VTT no se acepta

El archivo debe terminar en `.vtt` o `.txt` y tener marcas de tiempo. Un VTT valido contiene lineas parecidas a:

```text
00:00:00.000 --> 00:00:04.000
Texto del video.
```

## 7. Comprobar el resultado en la web

Cuando aparezca `COMPLETED`:

1. Recarga la pagina con `Ctrl+F5` si la lista no se actualiza.
2. Comprueba que el video muestra `X chunks`.
3. Verifica que esta activo y no aparece como `Inactivo`.
4. Haz una pregunta concreta sobre el contenido.
5. Pulsa una cita roja de la respuesta.
6. Comprueba que YouTube se abre en el minuto citado.

## 8. Repetir el proceso

Para cada video:

1. Copia su URL.
2. Descarga su `.vtt` desde Windows.
3. Introduce URL, titulo y archivo en Maisito.
4. Pulsa **Indexar transcripcion**.
5. Espera a `COMPLETED` y a que aparezca el numero de chunks.
6. Prueba una pregunta.

No borres el registro del video desde el icono de papelera salvo que quieras eliminarlo tambien del indice y del chat.

## 9. Se pueden borrar los archivos `.vtt`?

Si el video aparece como `COMPLETED` con chunks, puedes borrar el archivo `.vtt` de tu ordenador. Maisito ya ha guardado los fragmentos y no necesita el archivo original para responder.

Conserva una copia si quieres poder reindexar el video en el futuro sin volver a descargarlo.

No borres los volumenes Docker de PostgreSQL o Qdrant: contienen la informacion indexada de todos los videos.

## 10. Descargar todos los videos de una playlist

Si tienes una playlist, puedes descargar automaticamente la transcripcion de todos sus videos. `yt-dlp` los procesa uno detras de otro y crea un archivo `.vtt` separado para cada video.

En **CMD**, crea una carpeta y ejecuta el comando completo en una sola linea:

```cmd
mkdir vtt_playlist
cd vtt_playlist
py -m yt_dlp --yes-playlist --skip-download --write-subs --write-auto-subs --sub-langs "es.*,es" --sub-format vtt --convert-subs vtt --ignore-errors --no-overwrites -o "%(playlist_index)03d-%(id)s.%(ext)s" "URL_DE_LA_PLAYLIST"
```

Ejemplo:

```cmd
py -m yt_dlp --yes-playlist --skip-download --write-subs --write-auto-subs --sub-langs "es.*,es" --sub-format vtt --convert-subs vtt --ignore-errors --no-overwrites -o "%(playlist_index)03d-%(id)s.%(ext)s" "https://www.youtube.com/playlist?list=ID_DE_LA_PLAYLIST"
```

Se generaran archivos parecidos a estos:

```text
001-ID_VIDEO.es.vtt
002-ID_VIDEO.es.vtt
003-ID_VIDEO.es.vtt
```

Despues hay que subir cada `.vtt` individualmente en **Videotutoriales -> Importar transcripcion con tiempos** y esperar a que cada video llegue a `COMPLETED`.

En CMD se usa `%`, no `%%`. Los dos porcentajes solo se usan si el comando se guarda dentro de un archivo `.bat`.

## Resumen rapido

```text
Windows: descargar .vtt con py -m yt_dlp
Playlist: usar --yes-playlist para generar un .vtt por video
Web: Videotutoriales -> Importar transcripcion con tiempos
Web: introducir URL + titulo + archivo .vtt
Web: pulsar Indexar transcripcion
Esperar: PENDING -> PROCESSING -> COMPLETED
VPS: revisar logs con docker compose logs -f celery_worker
Probar: pregunta -> cita roja -> minuto exacto de YouTube
```
