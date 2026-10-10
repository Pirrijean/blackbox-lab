# Skill: Motor de Experimentación, Optimización y Análisis (Optuna + Data Stack)

## 1. Descripción y Propósito
Esta skill combina herramientas para consultar cajas negras como APIs o simuladores[cite: 1], almacenar resultados estructurados y optimizar variables utilizando métodos estadísticos y bayesianos sin conocer el funcionamiento interno del sistema evaluado[cite: 1].

## 2. Requisitos de Instalación (Instrucciones para el Agente Constructor)
Para implementar esta skill, el agente constructor debe preparar el entorno de experimentación ejecutando los siguientes pasos dentro de la raíz del proyecto `blackbox-lab`:

1.  **Inicializar el entorno de análisis de datos:**
    `uv venv`
    `source .venv/bin/activate`
2.  **Instalar el stack científico y de adaptadores:**
    `uv pip install httpx pydantic numpy pandas scipy matplotlib scikit-learn optuna pytest`
    *(Nota: `httpx` se utiliza como adaptador HTTPX para consultas externas, y las librerías matemáticas para el cálculo de métricas y validación predictiva[cite: 1]).*
3.  **Requisito externo:** Asegurar que Docker Desktop y Node.js están instalados en el sistema anfitrión.

## 3. Configuración MCP (El Contrato)
El agente constructor debe conectar estos servidores MCP para separar la ejecución de la evaluación de forma segura:

{
  "mcpServers": {
    "optuna-optimizer": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "./data:/app/data", "ghcr.io/optuna/optuna-mcp:latest"]
    },
    "fetch-api": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
    }
  }
}

## 4. Reglas de Uso de la Skill (Políticas)
*   **Separación de datos:** Conservar siempre las observaciones inmutables originales (salidas en bruto); los análisis y modelos aproximados se guardan como resultados derivados[cite: 1].
*   **Modelado aproximado:** Usar `scikit-learn` para aproximar la relación entre entradas observables y resultados, pero reconociendo que el modelo no replica la implementación interna de la caja negra[cite: 1].
*   **Optimización bayesiana:** Utilizar Optuna solo cuando cada consulta sea costosa y haya parámetros numéricos u otros espacios de búsqueda compatibles[cite: 1].
*   **Seguridad y Aislamiento:** Las ejecuciones de código (ej. simulaciones matemáticas) deben hacerse en entornos Docker aislados[cite: 1].