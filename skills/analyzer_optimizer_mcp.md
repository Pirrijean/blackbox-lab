# Skill: Blackbox Analyzer & Optimizer (Python MCP)

## Nombre
`blackbox-analyzer-optuna`

## Descripción
Servidor Model Context Protocol (MCP) personalizado basado en Python que expone las herramientas necesarias para la Evaluación, Aprendizaje y Optimización (Módulos 6, 7 y 8 de la arquitectura). Provee métodos de diseño de experimentos (ej. Latin Hypercube), análisis estadístico y optimización bayesiana a través de Optuna y Scikit-learn.

## Comando de Ejecución
```bash
uv run python src/blackbox_lab/mcp_servers/analyzer_optimizer.py
```

## Dependencias Requeridas
Este servidor requiere el entorno `uv` configurado con:
- `mcp`
- `optuna`
- `numpy`, `pandas`, `scipy`
- `scikit-learn`
- `pydantic`
- `matplotlib`

## Reglas de Seguridad y Restricciones
1. **Sin Alteración de Políticas:** Las funciones del optimizador (ej. sugerir siguiente prompt/input) están restringidas a recomendar; no pueden auto-aprobar ejecuciones si se exceden los `max_cost_usd` o el `budget`.
2. **Validación Pydantic:** Todas las entradas analizadas y los parámetros del modelo deben pasar la validación estricta de esquemas antes de iniciar la optimización.
3. **Evitar Conclusiones Falsas:** Las herramientas deben incorporar márgenes de confianza y alertar sobre multiplicidad. El modelo aproximado indicará siempre su nivel de incertidumbre.
4. **Detención Segura:** Si el presupuesto simulado o el timeout empírico se supera, la optimización debe devolver los resultados actuales y detenerse inmediatamente.
