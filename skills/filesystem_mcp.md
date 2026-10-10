# Skill: Filesystem MCP Server

## Nombre
`filesystem-mcp`

## Descripción
Servidor Model Context Protocol (MCP) para el manejo seguro y aislado del sistema de archivos local. Gestionará la escritura de evidencias masivas (archivos JSONL y Parquet), la lectura de configuraciones de experimentos (YAML) y los checkpoints de ejecución.

## Comando de Ejecución
```bash
npx -y @modelcontextprotocol/server-filesystem ./data ./configs ./reports
```

## Reglas de Seguridad y Restricciones
1. **Aislamiento de Directorios:** El servidor MCP solo podrá acceder a los directorios autorizados explícitamente (`./data`, `./configs`, `./reports`). No tiene acceso a claves del sistema o fuera del directorio del laboratorio.
2. **Registro de Sólo Anexado (JSONL/Parquet):** Los datos originales de entrada/salida se guardarán en formatos estructurados sin sobrescribir las pruebas previas.
3. **Separación de Datos:**
   - *Datos originales:* Almacenados en `./data/raw` (protegidos, inmutables).
   - *Datos derivados (métricas, gráficos):* Almacenados en `./data/derived` o `./reports` (se pueden regenerar).
4. **Límites de Ejecución:** El agente no podrá ejecutar código arbitrario guardado en estos directorios mediante este servidor MCP; es un servidor estrictamente de E/S.
