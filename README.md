# 🧪 blackbox-lab

> Plataforma de experimentación sistemática en sistemas de caja negra con inferencia estadística rigurosa, presupuestos acotados y almacenamiento inmutable de evidencia.

Diseñado para formular hipótesis, ejecutar experimentos iterativos y calcular incertidumbres estadísticas sin asumir respuestas puntuales exactas, preparado para el brief oficial de la hackathon.

---

## 🏗️ Arquitectura y Principios de Diseño

El laboratorio sigue una segregación de responsabilidades:
$$\text{Presupuesto} \longrightarrow \text{Diseño Experimental} \longrightarrow \text{Adaptador Aislado} \longrightarrow \text{Evidencia Inmutable} \longrightarrow \text{Métricas e Incertidumbre}$$

1. **Evidencia Inmutable (`execution/evidence.py`):** Los registros de entrada y respuesta bruta se almacenan de forma *append-only* en `data/raw/` con comprobación criptográfica SHA-256 para garantizar la integridad científica.
2. **Contabilidad Estricta de Presupuesto (`execution/budgets.py`):** Reservas y confirmaciones en `Decimal`. Detiene las consultas antes de sobrepasar el límite de coste fijado.
3. **Métricas con Distribución $t$ de Student (`core/metrics.py`):** Inferencia estadística sobre muestras pequeñas con intervalos de confianza al 95%, rechazando `NaN`, valores infinitos y declarando explícitamente sus límites.
4. **Adaptadores Aislados (`adapters/`):** Separación total entre la orquestación y el sistema evaluado. Incluye un `DeterministicSimulatorAdapter` para desarrollo offline y pruebas end-to-end con $0 de coste.
5. **Checkpoints Atómicos (`execution/checkpoints.py`):** Persistencia segura mediante archivos temporales y reemplazo atómico, con protección contra *path traversal*.

---

## 🚀 Inicio Rápido

### Requisitos previos
- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)

### 1. Instalación
```bash
git clone https://github.com/Pirrijean/blackbox-lab.git
cd blackbox-lab
uv sync
```

### 2. Diagnóstico del Entorno (`doctor`)
Verifica que el entorno, dependencias matemáticas y carpetas de datos estén preparadas:
```bash
uv run python main.py doctor
```

### 3. Ejecución de Simulación Local (End-to-End)
Ejecuta una optimización local determinista completa con registro de evidencia y cálculo de intervalos de confianza:
```bash
uv run python main.py run-simulation
```

### 4. Inspección de Métricas Estadísticas
Calcula el intervalo de Student para cualquier conjunto de mediciones:
```bash
uv run python main.py inspect-metrics 1.2 1.5 1.8 1.4 1.6
```

### 5. Adaptador Oficial para Evaluación (`entrypoint.py`)
Listo para conectarse al contrato del evaluador del evento:
```bash
uv run python -m blackbox_lab.entrypoint --health
```

---

## 🧪 Pruebas Automatizadas

```bash
uv run pytest
```
Cubre validación de contratos no desactivables, rechazo de claves JSON duplicadas, durabilidad de checkpoints, orquestador de experimentos y cálculo de incertidumbre.
