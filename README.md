# MAIS_IA - Asistente RAG con Personalidad de Maisito (Pack Portable)

Este es el backend y el panel de control local del asistente inteligente RAG (Retrieval-Augmented Generation) para el manual de **MAIS**.

El sistema es completamente **portable** y dinámico. Al utilizar rutas relativas y variables cargadas de forma local, puedes mover esta carpeta completa a cualquier ordenador y funcionará sin tener que alterar las configuraciones internas de Windows.

---

## 🛠️ Arquitectura y Tecnologías
* **Motor Backend:** Python 3.14+ (FastAPI).
* **Base de Datos Vectorial:** Qdrant (almacén de embeddings semánticos y por palabras clave).
* **Cola de Ingesta Asíncrona:** Celery (con Redis como broker de mensajes).
* **Base de Datos Relacional:** PostgreSQL (historial y metadatos).
* **Controlador de Túnel:** Ngrok (para exponer el servidor local a internet).

---

## 🚀 Requisitos para Servidor Local (Otro Ordenador)
Si quieres copiar este proyecto a otro ordenador (por ejemplo, mediante un pendrive) para que actúe como servidor local conectado a la web de OVH, ese ordenador debe tener instalado previamente:

1. **Docker Desktop** (para arrancar las bases de datos).
2. **Python 3.14+** (instalado de forma global en Windows, marcando la opción *"Add python.exe to PATH"* en el instalador).
3. **Node.js y npm** (para compilar y ejecutar el frontend local de subida de archivos).

---

## 📋 Pasos de Configuración en el Nuevo Ordenador

### Paso 1: Copiar la carpeta y el archivo `.env`
Copia la carpeta entera `MAIS_IA` al disco local del nuevo ordenador (se recomienda el Escritorio para mayor velocidad).
> [!IMPORTANT]  
> Asegúrate de que el archivo `.env` esté dentro de la carpeta `backend/`. Debe contener tu API Key de Groq, la configuración de puertos y tu token de Ngrok:
> ```env
> POSTGRES_PORT=5433
> REDIS_PORT=6380
> CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000", "https://maisformacion.com"]
> GROQ_API_KEY=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
> NGROK_AUTHTOKEN=3IAnRwu81jvyTzONXlQixB0ItNz_58cQHab69cxu7j1c3xhVa
> ```

### Paso 2: Colocar Ngrok
Descarga Ngrok para Windows y extrae el archivo **`ngrok.exe`** directamente en la raíz de esta carpeta (en el mismo nivel donde está `start_mais_ia.bat`). 

*(Ya no necesitas registrar el token con comandos ni guardarlo en las carpetas del sistema. El script `.bat` leerá automáticamente la variable `NGROK_AUTHTOKEN` de tu `.env` local antes de abrir el túnel).*

### Paso 3: Crear el Entorno Virtual e Instalar Librerías (Solo la primera vez)
Abre una consola (CMD) en el nuevo ordenador y ejecuta estos comandos para crear las dependencias de forma aislada e independiente en el proyecto:

1. **Backend (Python .venv):**
   ```cmd
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Frontend (Node.js):**
   ```cmd
   cd ../frontend
   npm install
   ```

### Paso 4: Arrancar los servicios
1. Abre **Docker Desktop** en el nuevo ordenador.
2. Ejecuta el archivo **`start_mais_ia.bat`** haciendo doble clic.
3. Se abrirán 4 terminales independientes levantando las bases de datos en Docker, Celery, el Backend de FastAPI (conectado a tu entorno virtual `.venv`), el Frontend en Next.js y el túnel de Ngrok cargando tus credenciales del `.env` local.

---

## 💻 Panel de Ingesta (http://localhost:3000)
Una vez arrancado, entra en [http://localhost:3000](http://localhost:3000) en el ordenador servidor:
* Desde aquí podrás **arrastrar y subir los manuales en PDF** (ej: `ALBARAN_A_FACTURA.pdf`).
* Celery procesará el PDF en segundo plano y lo guardará en la base de datos de vectores.
* En cuanto ponga "Completado", el chat de la web de OVH ya tendrá conocimiento de ese archivo.
