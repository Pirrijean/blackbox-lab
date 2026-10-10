import os
import sys
from pathlib import Path


def run_doctor() -> bool:
    """Verifica el entorno de ejecución de blackbox-lab sin gastar dinero ni lanzar experimentos."""
    print("==================================================")
    print("[*] DIAGNOSTICO DEL ENTORNO: blackbox-lab")
    print("==================================================")

    all_ok = True

    # 1. Versión de Python
    py_version = sys.version_info
    py_ok = py_version >= (3, 12)
    print(f"[{'OK' if py_ok else 'FAIL'}] Python >= 3.12: {sys.version.split()[0]}")
    if not py_ok:
        all_ok = False

    # 2. Dependencias críticas para análisis estadístico y simulación
    deps = ["numpy", "scipy", "pydantic", "httpx", "pytest"]
    for dep in deps:
        try:
            __import__(dep)
            print(f"[OK] Dependencia '{dep}': instalada")
        except ImportError:
            print(f"[FAIL] Dependencia '{dep}': NO encontrada")
            all_ok = False

    # 3. Directorios de datos segregados (raw / derived / checkpoints)
    dirs = [
        Path("./data/raw"),
        Path("./data/derived"),
        Path("./data/checkpoints"),
    ]
    for d in dirs:
        d.resolve().mkdir(parents=True, exist_ok=True)
        is_writable = os.access(d, os.W_OK)
        print(f"[{'OK' if is_writable else 'FAIL'}] Directorio con permisos: {d}")
        if not is_writable:
            all_ok = False

    # 4. Verificación de variables de entorno
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key and len(api_key.strip()) > 5:
        masked = f"{api_key[:4]}...{api_key[-3:]}"
        print(f"[OK] Variable OPENROUTER_API_KEY: Configurada ({masked})")
    else:
        print("[INFO] Variable OPENROUTER_API_KEY: No configurada (Modo simulacion / offline disponible)")

    print("==================================================")
    if all_ok:
        print("[EXITO] Entorno de desarrollo verificado y listo para operar.")
    else:
        print("[ALERTA] Se encontraron problemas en el entorno. Revisa los mensajes anteriores.")
    print("==================================================")

    return all_ok


if __name__ == "__main__":
    success = run_doctor()
    sys.exit(0 if success else 1)
