# MAIS_IA - Asistente RAG con Personalidad de Maisito

Este es el backend y el panel de control local del asistente inteligente RAG (Retrieval-Augmented Generation) para el manual de **MAIS**.

El sistema procesa y segmenta documentos en PDF en un almacén de vectores local (Qdrant), calcula las similitudes híbridas (semántica y por palabras clave), reordena los fragmentos y utiliza un LLM externo (Groq) con la personalidad de **Maisito** para resolver consultas directamente.

---

## 🛠️ Arquitectura y Tecnologías
* **Motor Backend:** Python 3.14+ (FastAPI).
* **Base de Datos Vectorial:** Qdrant (almacén de embeddings densos y esparsos).
* **Cola de Ingesta Asíncrona:** Celery (con Redis como broker de mensajes).
* **Base de Datos Relacional:** PostgreSQL (historial y metadatos).
* **Controlador de Túnel:** Ngrok (para exponer el servidor local a internet).

---

## 🚀 Requisitos para Servidor Local (Otro Ordenador)
Si quieres empaquetar esta carpeta y pasarla a otro ordenador para que haga la función de "Servidor Local" conectado a la web de OVH, ese ordenador debe tener instalado:

1. **Docker Desktop** (para levantar las bases de datos).
2. **Python 3.14+** (instalado de forma global en Windows, marcando la opción *"Add python.exe to PATH"* en el instalador).
3. **Node.js y npm** (para compilar y ejecutar el frontend local de subida de archivos).
4. **Túnel Ngrok** (el token de autenticación configurado).

---

## 📋 Pasos de Instalación en el Nuevo Ordenador

### Paso 1: Copiar la carpeta y el archivo `.env`
Copia la carpeta entera `MAIS_IA` al escritorio del nuevo equipo. 
> [!IMPORTANT]  
> Asegúrate de copiar manualmente el archivo `.env` de la carpeta `backend/` (ya que Git lo ignora por motivos de seguridad y no se descargará de GitHub). Debe contener tu API Key de Groq y la configuración de puertos:
> ```env
> POSTGRES_PORT=5433
> REDIS_PORT=6380
> CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000", "https://maisformacion.com"]
> GROQ_API_KEY=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
> ```

### Paso 2: Descargar e Instalar Ngrok
1. Descarga Ngrok para Windows desde la web oficial.
2. Descomprímelo y mete el archivo `ngrok.exe` dentro de la carpeta oculta `C:\Users\usuario\AppData\Local\ngrok\ngrok.exe` (o modifica el archivo `start_mais_ia.bat` para apuntar a la ruta donde lo pongas).
3. Registra el authtoken de tu cuenta de Ngrok ejecutando en la consola (CMD) del nuevo ordenador:
   ```cmd
   C:\Users\usuario\AppData\Local\ngrok\ngrok.exe config add-authtoken <TU_TOKEN>
   ```

### Paso 3: Instalar dependencias de Python y Node.js
Para instalar las librerías necesarias del sistema en el nuevo ordenador, abre una consola (CMD) y ejecuta los siguientes comandos:

1. **Dependencias del Backend (Python):**
   Navega a la carpeta de `backend` y ejecuta:
   ```cmd
   cd backend
   pip install -r requirements.txt
   ```
2. **Dependencias del Frontend (Node.js):**
   Vuelve a la raíz, navega a la carpeta de `frontend` y ejecuta:
   ```cmd
   cd ../frontend
   npm install
   ```

### Paso 4: Arrancar los servicios
1. Abre **Docker Desktop** en el nuevo ordenador.
2. Ejecuta el archivo **`start_mais_ia.bat`** haciendo doble clic.
3. Se abrirán 4 terminales ejecutando las bases de datos (Postgres, Redis, Qdrant), Celery, FastAPI, el panel de Next.js y el túnel de Ngrok de forma automática y simultánea.

---

## 💻 Panel de Ingesta (http://localhost:3000)
Una vez arrancado, entra en [http://localhost:3000](http://localhost:3000) en el ordenador servidor:
* Desde aquí podrás **arrastrar y subir los manuales en PDF** (ej: `ALBARAN_A_FACTURA.pdf`).
* Celery procesará el PDF en segundo plano y lo guardará en la base de datos de vectores.
* En cuanto ponga "Completado", el chat de la web de OVH ya tendrá conocimiento de ese archivo.
