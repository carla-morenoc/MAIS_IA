import subprocess
import re
import urllib.request
import urllib.parse
import time
import sys

# Configuracion
OVH_UPDATE_URL = "https://maisformacion.com/BACKEND/update_tunnel.php"
SECRET_TOKEN = "mais_ia_secreto_2026"
PORT = 8000
SUBDOMAIN = "api-mais-ia"

print(f"Iniciando LocalTunnel en el puerto {PORT}...")

# Ejecutar localtunnel
# npx localtunnel --port 8000 --subdomain api-mais-ia
process = subprocess.Popen(
    ["cmd", "/c", f"npx localtunnel --port {PORT} --subdomain {SUBDOMAIN}"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    universal_newlines=True
)

url_found = False

try:
    for line in process.stdout:
        print(line, end="")
        
        # Buscar la URL en la salida
        if not url_found and "your url is:" in line:
            # Extraer la URL
            match = re.search(r'https?://[^\s]+', line)
            if match:
                tunnel_url = match.group(0)
                print(f"\n[+] URL Detectada: {tunnel_url}")
                print("[+] Registrando URL en el servidor de OVH...")
                
                # Enviar a OVH
                data = urllib.parse.urlencode({
                    'token': SECRET_TOKEN,
                    'url': tunnel_url
                }).encode('utf-8')
                
                req = urllib.request.Request(OVH_UPDATE_URL, data=data)
                try:
                    with urllib.request.urlopen(req, timeout=10) as response:
                        result = response.read().decode('utf-8')
                        print(f"[+] Respuesta de OVH: {result}")
                        print("\n=======================================================")
                        print(" LISTO: LA PAGINA WEB YA ESTA CONECTADA A ESTE ORDENADOR ")
                        print(" (No cierres esta ventana negra mientras quieras que funcione)")
                        print("=======================================================\n")
                except Exception as e:
                    print(f"[-] Error al registrar en OVH: {e}")
                
                url_found = True
except KeyboardInterrupt:
    print("\nCerrando túnel...")
    process.terminate()
    sys.exit(0)
