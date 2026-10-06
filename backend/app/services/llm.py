"""
MAIS_IA — Servicio LLM centralizado.

Soporta:
1. OpenAI (Cloud comercial)
2. Groq (Cloud ultrarrápido y gratuito)
3. Ollama (Inferencia local)
4. Mock (Desarrollo local sin dependencias)
"""

import asyncio
import logging
import random
import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMUnavailableError(RuntimeError):
    """Error seguro para el usuario cuando un proveedor LLM no está disponible."""


class LLMService:
    """Servicio para interactuar con LLMs locales (Ollama), cloud (OpenAI/Groq) o simulados (Mock)."""

    def __init__(self) -> None:
        self.provider = settings.llm_provider.lower()
        self.model = settings.llm_model
        self.base_url = settings.ollama_base_url
        self.openai_key = settings.openai_api_key
        self.groq_key = settings.groq_api_key
        self.gemini_key = settings.gemini_api_key
        self.deepseek_key = settings.deepseek_api_key

        # Validar conectividad con los proveedores activos, si no hay credenciales, cae en Mock
        self._detect_best_provider()

    def _detect_best_provider(self) -> None:
        """Verifica la conectividad y ajusta el proveedor si es necesario."""
        if self.provider == "openai" and not self.openai_key:
            logger.warning("OPENAI_API_KEY no configurada. Activando proveedor 'mock' para desarrollo local.")
            self.provider = "mock"

        elif self.provider == "groq" and not self.groq_key:
            logger.warning("GROQ_API_KEY no configurada. Activando proveedor 'mock' para desarrollo local.")
            self.provider = "mock"

        elif self.provider == "gemini" and not self.gemini_key:
            logger.warning("GEMINI_API_KEY no configurada. Activando proveedor 'mock' para desarrollo local.")
            self.provider = "mock"

        elif self.provider == "deepseek" and not self.deepseek_key:
            logger.warning("DEEPSEEK_API_KEY no configurada. Activando proveedor 'mock' para desarrollo local.")
            self.provider = "mock"
        
        elif self.provider == "ollama":
            # Test rápido de conexión síncrona
            try:
                with httpx.Client(timeout=1.0) as client:
                    r = client.get(self.base_url)
                    if r.status_code != 200:
                        raise httpx.ConnectError("Ollama no devolvió 200 OK")
            except Exception:
                logger.warning(
                    "No se detectó Ollama corriendo en %s. "
                    "Activando proveedor 'mock' temporalmente para verificar el pipeline.",
                    self.base_url
                )
                self.provider = "mock"

        logger.info(
            "Servicio LLM inicializado. Proveedor final: %s, Modelo: %s",
            self.provider,
            self.model,
        )

    async def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        """Genera una respuesta de texto basada en un prompt y un system prompt opcional."""
        try:
            return await self._call_provider(self.provider, prompt, system_prompt)
        except LLMUnavailableError:
            # Un proveedor alternativo solo se usa si ya tiene una clave configurada.
            # Así Gemini no deja el chat caído durante una incidencia temporal.
            for provider in self._available_fallbacks():
                try:
                    logger.warning("Proveedor %s no disponible; probando respaldo %s.", self.provider, provider)
                    return await self._call_provider(provider, prompt, system_prompt)
                except LLMUnavailableError:
                    logger.warning("Proveedor de respaldo %s no disponible.", provider)
            raise

    async def _call_provider(self, provider: str, prompt: str, system_prompt: str) -> str:
        if provider == "openai":
            return await self._call_openai(prompt, system_prompt)
        if provider == "groq":
            return await self._call_groq(prompt, system_prompt)
        if provider == "gemini":
            return await self._call_gemini(prompt, system_prompt)
        if provider == "deepseek":
            return await self._call_deepseek(prompt, system_prompt)
        if provider == "ollama":
            return await self._call_ollama(prompt, system_prompt)
        if provider == "mock":
            return await self._call_mock(prompt)
        raise ValueError(f"Proveedor de LLM no soportado: '{provider}'")

    def _available_fallbacks(self) -> list[str]:
        configured = {
            "openai": bool(self.openai_key),
            "groq": bool(self.groq_key),
            "gemini": bool(self.gemini_key),
            "deepseek": bool(self.deepseek_key),
        }
        return [name for name in ("groq", "gemini", "deepseek", "openai") if name != self.provider and configured[name]]

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        """Respeta Retry-After cuando existe y evita reintentos simultáneos."""
        retry_after = response.headers.get("Retry-After") if response is not None else None
        try:
            return min(float(retry_after), 15.0) if retry_after else min(2 ** attempt, 8.0) + random.random()
        except ValueError:
            return min(2 ** attempt, 8.0) + random.random()

    async def rewrite_query(self, query: str, history: list[dict[str, str]] | None = None) -> str:
        """Reescribe una consulta de usuario para optimizar la recuperación semántica con contexto conversacional."""
        if self.provider == "mock":
            # Mock de reescritura simple agregando sinónimos de RAG
            logger.info("Mocking query rewrite...")
            return f"{query} Hybrid Search Retrieval Corrective RAG"

        history_str = ""
        if history:
            history_lines = []
            for t in history[-4:]:
                role_label = 'Usuario' if t.get('role') == 'user' else 'Maisito'
                content = t.get('content', '')
                if len(content) > 400:
                    content = content[:400] + "..."
                history_lines.append(f"{role_label}: {content}")
            history_str = f"Historial de conversación previo:\n" + "\n".join(history_lines) + "\n\n"

        system_prompt = (
            "Eres un asistente de recuperación de información de nivel experto. "
            "Tu tarea es analizar la consulta del usuario (y el historial si lo hay) y reescribirla de forma clara, "
            "eliminando ambigüedades, reemplazando pronombres ('eso', 'el anterior', 'lo') por los conceptos reales "
            "y añadiendo términos clave relacionados de los programas MAIS para mejorar la búsqueda semántica. "
            "Devuelve ÚNICAMENTE la consulta reescrita, sin introducciones, sin explicaciones y sin comillas."
        )
        prompt = f"{history_str}Consulta del usuario a reformular: {query}"
        
        try:
            rewritten = await self.generate_response(prompt, system_prompt)
            rewritten_clean = rewritten.strip().replace('"', '').replace("'", "")
            logger.info("Consulta reescrita de '%s' a '%s'", query, rewritten_clean)
            return rewritten_clean
        except Exception as exc:
            logger.warning("Fallo al reescribir la consulta: %s. Usando original.", exc)
            return query

    async def expand_retrieval_terms(self, query: str) -> str:
        """Genera vocabulario de recuperación en español sin responder al usuario."""
        if self.provider == "mock":
            return query

        system_prompt = (
            "Eres un componente interno de recuperación para manuales y vídeos "
            "de software de facturación MAIS. No respondas la pregunta. Devuelve "
            "solo una línea de 6 a 16 términos o expresiones cortas en español, "
            "separados por comas, que podrían aparecer literalmente en el manual "
            "o transcripción que responde a la consulta. Conserva los conceptos "
            "del usuario y añade sinónimos funcionales, singular/plural y nombres "
            "probables de menú o informe. No incluyas saludos, explicaciones ni "
            "palabras genéricas como 'programa', 'pantalla' o 'ayuda'."
        )
        try:
            expansion = await self.generate_response(
                f"Consulta: {query}",
                system_prompt,
            )
            # Una respuesta anómala no puede inflar la consulta ni cambiar el
            # comportamiento de la recuperación.
            expansion = " ".join(expansion.replace("\n", " ").split())[:500]
            if not expansion:
                return query
            logger.info("Términos de recuperación ampliados: '%s'", expansion)
            return f"{query} {expansion}"
        except Exception as exc:
            logger.warning("No se pudo ampliar la consulta; se usa el texto original: %s", exc)
            return query

    async def _call_ollama(self, prompt: str, system_prompt: str) -> str:
        """Realiza una llamada asíncrona a la API local de Ollama."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {"temperature": 0.0}
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return str(data["response"]).strip()
            except Exception as exc:
                logger.error("Error conectando con Ollama: %s", exc)
                raise

    async def _call_openai(self, prompt: str, system_prompt: str) -> str:
        """Realiza una llamada asíncrona a la API oficial de OpenAI."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        openai_model = self.model
        if openai_model in {"gemini", "gemini-3.5-flash-lite", "deepseek", "deepseek-chat", "mock"}:
            openai_model = "gpt-4o-mini"
        payload = {
            "model": openai_model,
            "messages": messages,
            "temperature": 0.0,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return str(data["choices"][0]["message"]["content"]).strip()
            except httpx.HTTPStatusError as exc:
                logger.error("OpenAI respondió HTTP %s.", exc.response.status_code)
                raise LLMUnavailableError("OpenAI no está disponible temporalmente.") from exc
            except httpx.HTTPError as exc:
                logger.error("Error de red conectando con OpenAI: %s", type(exc).__name__)
                raise LLMUnavailableError("OpenAI no está disponible temporalmente.") from exc

    async def _call_groq(self, prompt: str, system_prompt: str) -> str:
        """Realiza una llamada asíncrona a la API oficial de Groq (OpenAI-compatible)."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json",
        }
        
        # Mapear modelos estándar a modelos activos y soportados en Groq
        groq_model = self.model
        if groq_model in ["llama3", "llama", "llama-3", "mock", "llama-3.1-8b-instant", "gemini", "gemini-3.5-flash-lite"]:
            groq_model = "openai/gpt-oss-120b"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": groq_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1600,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(3):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    msg_obj = data["choices"][0]["message"]
                    content = msg_obj.get("content") or msg_obj.get("reasoning") or ""
                    if not content:
                        raise LLMUnavailableError("Groq no devolvió contenido utilizable.")
                    return str(content).strip()
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    transient = status in (408, 429) or status >= 500
                    if not transient or attempt == 2:
                        logger.error("Groq respondió HTTP %s.", status)
                        raise LLMUnavailableError("Groq no está disponible temporalmente.") from exc
                    delay = self._retry_delay(exc.response, attempt)
                    logger.warning(
                        "Groq respondió HTTP %s; reintentando en %.1f s (%d/3).",
                        status,
                        delay,
                        attempt + 1,
                    )
                    await asyncio.sleep(delay)
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        logger.error("Error de red con Groq tras %d intentos: %s", attempt + 1, type(exc).__name__)
                        raise LLMUnavailableError("Groq no está disponible temporalmente.") from exc
                    delay = self._retry_delay(None, attempt)
                    logger.warning("Error de red con Groq; reintentando en %.1f s.", delay)
                    await asyncio.sleep(delay)
                except (IndexError, KeyError, TypeError, ValueError) as exc:
                    logger.error("Groq devolvió una respuesta no utilizable: %s", type(exc).__name__)
                    raise LLMUnavailableError("Groq no devolvió contenido utilizable.") from exc

    async def _call_gemini(self, prompt: str, system_prompt: str) -> str:
        """Realiza una llamada asíncrona a la API de Google AI Studio (Gemini)."""
        gemini_model = self.model
        if gemini_model in ["gemini", "mock", "openai/gpt-oss-120b", "llama3", "llama-3.1-8b-instant", "deepseek-chat"]:
            gemini_model = "gemini-3.5-flash-lite"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={self.gemini_key}"
        
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096,
            }
        }
        
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(3):
                response: httpx.Response | None = None
                try:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise LLMUnavailableError("Gemini no devolvió contenido utilizable.")
                    return str(candidates[0]["content"]["parts"][0]["text"]).strip()
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    # 4xx de credenciales/permisos no se solucionan reintentando.
                    if status not in (408, 429) and status < 500:
                        logger.error("Gemini respondió HTTP %s.", status)
                        raise LLMUnavailableError("La configuración de Gemini no permite generar respuestas.") from exc
                    if attempt == 2:
                        logger.error("Gemini sigue no disponible tras %d intentos (HTTP %s).", attempt + 1, status)
                        raise LLMUnavailableError("Gemini no está disponible temporalmente.") from exc
                    delay = self._retry_delay(exc.response, attempt)
                    logger.warning("Gemini respondió HTTP %s; reintentando en %.1f s.", status, delay)
                    await asyncio.sleep(delay)
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        logger.error("Error de red con Gemini tras %d intentos: %s", attempt + 1, type(exc).__name__)
                        raise LLMUnavailableError("Gemini no está disponible temporalmente.") from exc
                    delay = self._retry_delay(response, attempt)
                    logger.warning("Error de red con Gemini; reintentando en %.1f s.", delay)
                    await asyncio.sleep(delay)

    async def _call_deepseek(self, prompt: str, system_prompt: str) -> str:
        """Realiza una llamada asíncrona a la API oficial de DeepSeek (compatible con OpenAI)."""
        ds_model = self.model
        if ds_model in ["deepseek", "mock", "openai/gpt-oss-120b", "llama3", "llama-3.1-8b-instant", "gemini-1.5-flash", "gemini", "gemini-3.5-flash-lite"]:
            ds_model = "deepseek-chat"

        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.deepseek_key}",
            "Content-Type": "application/json",
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": ds_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return str(data["choices"][0]["message"]["content"]).strip()
            except httpx.HTTPStatusError as exc:
                logger.error("DeepSeek respondió HTTP %s.", exc.response.status_code)
                raise LLMUnavailableError("DeepSeek no está disponible temporalmente.") from exc
            except httpx.HTTPError as exc:
                logger.error("Error de red conectando con DeepSeek: %s", type(exc).__name__)
                raise LLMUnavailableError("DeepSeek no está disponible temporalmente.") from exc

    async def _call_mock(self, prompt: str) -> str:
        """Genera una respuesta simulada inteligente basada en los fragmentos del prompt."""
        # Extraer fragmentos del prompt para construir una respuesta simulada con citas correctas
        lines = prompt.split("\n")
        files_found = []
        snippets = []

        current_file = ""
        current_page = ""
        
        for line in lines:
            if line.startswith("Archivo:"):
                current_file = line.split(":", 1)[1].strip()
            elif line.startswith("Página:"):
                current_page = line.split(":", 1)[1].strip()
            elif line.startswith("Contenido:"):
                content = line.split(":", 1)[1].strip()
                if current_file and current_page:
                    files_found.append((current_file, current_page))
                    snippets.append(content)
                    current_file = ""
                    current_page = ""

        if not snippets:
            return "Lo siento, no he encontrado información en los fragmentos provistos para responder."

        # Simular una respuesta estructurada
        answer_parts = []
        if "implement" in prompt.lower() or "what" in prompt.lower():
            answer_parts.append(
                f"De acuerdo a la documentación, MAIS_IA implementa Búsqueda Híbrida y Re-Ranking "
                f"junto con un sistema de Ingestión Asíncrona [{files_found[0][0]}, pág. {files_found[0][1]}]."
            )
            if len(files_found) > 1:
                answer_parts.append(
                    f"Adicionalmente, se menciona que el pipeline de ingestión divide el texto en chunks y "
                    f"genera los embeddings de forma local con FastEmbed ejecutándose en CPU [{files_found[1][0]}, pág. {files_found[1][1]}]."
                )
        else:
            answer_parts.append(
                f"Información recuperada del documento: {snippets[0][:150]}... "
                f"[{files_found[0][0]}, pág. {files_found[0][1]}]."
            )

        return " ".join(answer_parts)


# Instancia singleton para uso en toda la aplicación
llm_service = LLMService()


def get_llm_service() -> LLMService:
    """Retorna la instancia singleton del servicio LLM."""
    return llm_service
