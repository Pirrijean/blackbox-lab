# Skill: SQLite MCP Server

## Nombre
`sqlite-mcp`

## Descripción
Servidor Model Context Protocol (MCP) oficial para la gestión de bases de datos SQLite. En la plataforma `blackbox-lab`, se utiliza para registrar los metadatos de los experimentos, el estado inicial de las ejecuciones, y gestionar los límites de presupuesto y autorizaciones (Módulos 1, 3 y 5 de la arquitectura).

## Comando de Ejecución
```bash
npx -y @modelcontextprotocol/server-sqlite --db-path ./data/blackbox_metadata.db
```

## Reglas de Seguridad y Restricciones
1. **Inmutabilidad de la Evidencia Original:** La base de datos registrará el historial de operaciones, pero los datos originales (entradas y salidas) no deben sobrescribirse. Los análisis y modelos aproximados se guardarán como resultados derivados.
2. **Protección de Secretos:** No se almacenarán claves de API (OpenAI, Anthropic, etc.) ni tokens de autenticación en la base de datos de texto plano.
3. **Control del Optimizador:** El agente optimizador NO tiene permisos para alterar las tablas que definen los límites de coste (`budgets`) ni los permisos (`policies`). Solo tiene permisos de lectura sobre estas y permisos de escritura para registrar sus propuestas.
4. **Trazabilidad:** Cada operación debe poder reconstruirse. Debe existir una tabla de auditoría inmutable vinculada al `experiment_id` y `run_id`.
