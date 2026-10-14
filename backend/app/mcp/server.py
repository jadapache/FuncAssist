"""FuncAssist Model Context Protocol (MCP) Server.

Implements the official MCP 2024-11-05 standard specification for exposing
FuncAssist RAG knowledge, corporate templates, document agent operations,
and QA test plan tools to external agentic models (Claude Desktop, Cursor, Antigravity, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.mcp.schema import (
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    MCPResource,
    MCPResourceContent,
    MCPTool,
    MCPToolCallResult,
    MCPToolContent,
)

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"


class FuncAssistMCPServer:
    """Core MCP Server for FuncAssist."""

    def __init__(self) -> None:
        self.server_info = {
            "name": "funcassist-mcp-server",
            "version": "1.0.0",
        }
        self.capabilities = {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
        }

    def get_tools(self) -> List[MCPTool]:
        """Returns the registered tools conforming to MCP schema."""
        return [
            MCPTool(
                name="funcassist_search_knowledge",
                description=(
                    "Busca información relevante en la base de conocimiento corporativa y RAG de FuncAssist "
                    "(manuales de usuario, requerimientos funcionales, PRDs, reglas de negocio)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Texto o pregunta de búsqueda en la base de conocimiento.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Número máximo de fragmentos relevantes a retornar (por defecto 5).",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            ),
            MCPTool(
                name="funcassist_list_templates",
                description=(
                    "Lista las plantillas corporativas oficiales de FuncAssist disponibles "
                    "para levantamiento de mejoras, documentación funcional y pruebas QA."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "module": {
                            "type": "string",
                            "description": "Filtro opcional por módulo ('mejoras', 'funcional', 'qa', 'inventario').",
                        },
                    },
                },
            ),
            MCPTool(
                name="funcassist_plan_document_operations",
                description=(
                    "Agente de edición documental estructurada: Traduce una solicitud en operaciones canónicas "
                    "(insert_text, insert_image, replace_content, update_table) para Univer y Word/Excel."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Instrucción de cambio o contenido a redactar en el documento.",
                        },
                        "current_document": {
                            "type": "string",
                            "description": "Texto actual o contexto del documento en edición.",
                        },
                        "section": {
                            "type": "string",
                            "description": "Sección específica objetivo (ej. 'Observaciones', 'Requerimientos Funcionales').",
                        },
                    },
                    "required": ["prompt"],
                },
            ),
            MCPTool(
                name="funcassist_create_qa_test_plan",
                description=(
                    "Genera una matriz y plan estructurado de pruebas QA (casos de prueba, precondiciones, pasos, resultado esperado) "
                    "para una funcionalidad o requerimiento."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "feature_name": {
                            "type": "string",
                            "description": "Nombre o identificador de la funcionalidad a testear.",
                        },
                        "description": {
                            "type": "string",
                            "description": "Descripción del requerimiento o cambios realizados.",
                        },
                        "test_type": {
                            "type": "string",
                            "description": "Tipo de prueba: 'regression', 'integration', 'smoke', 'security'.",
                            "default": "regression",
                        },
                    },
                    "required": ["feature_name", "description"],
                },
            ),
            MCPTool(
                name="funcassist_summarize_standup",
                description=(
                    "Genera un reporte diario estructurado de avance y bloqueos (Daily Standup) "
                    "para el seguimiento del Director de Proyecto (PM)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "yesterday": {
                            "type": "string",
                            "description": "¿Qué tareas o historias se completaron ayer?",
                        },
                        "today": {
                            "type": "string",
                            "description": "¿Qué tareas o historias se trabajarán hoy?",
                        },
                        "blockers": {
                            "type": "string",
                            "description": "Bloqueos, impedimentos o dependencias encontradas.",
                            "default": "Sin bloqueos identificados.",
                        },
                        "project": {
                            "type": "string",
                            "description": "Nombre del proyecto o módulo asociado.",
                        },
                    },
                    "required": ["yesterday", "today"],
                },
            ),
        ]

    def get_resources(self) -> List[MCPResource]:
        """Returns the registered resources conforming to MCP schema."""
        return [
            MCPResource(
                uri="funcassist://knowledge/index",
                name="Índice de Base de Conocimiento",
                description="Catálogo de fuentes y documentos indexados en el RAG de FuncAssist.",
                mimeType="application/json",
            ),
            MCPResource(
                uri="funcassist://templates/fixtures",
                name="Plantillas Corporativas Fixtures",
                description="Listado de formatos Word y Excel oficiales para documentos corporativos.",
                mimeType="application/json",
            ),
        ]

    async def handle_request(self, req: JSONRPCRequest) -> JSONRPCResponse:
        """Processes an incoming JSON-RPC request and returns the appropriate response."""
        req_id = req.id

        try:
            if req.method == "initialize":
                return JSONRPCResponse(
                    id=req_id,
                    result={
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": self.capabilities,
                        "serverInfo": self.server_info,
                    },
                )

            elif req.method == "ping":
                return JSONRPCResponse(id=req_id, result={})

            elif req.method == "tools/list":
                tools = [t.model_dump() for t in self.get_tools()]
                return JSONRPCResponse(id=req_id, result={"tools": tools})

            elif req.method == "tools/call":
                params = req.params or {}
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = await self.execute_tool(tool_name, arguments)
                return JSONRPCResponse(id=req_id, result=result.model_dump())

            elif req.method == "resources/list":
                resources = [r.model_dump() for r in self.get_resources()]
                return JSONRPCResponse(id=req_id, result={"resources": resources})

            elif req.method == "resources/read":
                params = req.params or {}
                uri = params.get("uri", "")
                resource_content = await self.read_resource(uri)
                return JSONRPCResponse(id=req_id, result={"contents": [resource_content.model_dump()]})

            elif req.method == "prompts/list":
                return JSONRPCResponse(id=req_id, result={"prompts": []})

            else:
                return JSONRPCResponse(
                    id=req_id,
                    error=JSONRPCError(code=-32601, message=f"Method not found: {req.method}"),
                )

        except Exception as ex:
            logger.exception("Error processing MCP request method %s", req.method)
            return JSONRPCResponse(
                id=req_id,
                error=JSONRPCError(code=-32603, message=f"Internal MCP error: {str(ex)}"),
            )

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> MCPToolCallResult:
        """Executes a FuncAssist tool on behalf of the MCP client."""
        try:
            if name == "funcassist_search_knowledge":
                query = args.get("query", "")
                top_k = int(args.get("top_k", 5))
                from app.context.retrieval import search_knowledge

                chunks = search_knowledge(query, top_k=top_k)
                if not chunks:
                    return MCPToolCallResult(
                        content=[
                            MCPToolContent(
                                type="text",
                                text=f"No se encontraron fragmentos relevantes para la consulta: '{query}'.",
                            )
                        ]
                    )

                text_blocks = []
                for idx, c in enumerate(chunks, 1):
                    title = c.title or c.source_label or f"Documento #{idx}"
                    text_blocks.append(f"### [{idx}] {title}\n{c.text}\n")

                output = f"Resultados encontrados ({len(chunks)} fragmentos):\n\n" + "\n".join(text_blocks)
                return MCPToolCallResult(content=[MCPToolContent(type="text", text=output)])

            elif name == "funcassist_list_templates":
                from app.core.template_storage import list_templates

                templates = list_templates()
                mod_filter = (args.get("module") or "").lower().strip()
                if mod_filter:
                    templates = [
                        t for t in templates
                        if mod_filter in (t.get("module") or "").lower() or mod_filter in (t.get("title") or "").lower()
                    ]

                simplified = [
                    {
                        "id": t.get("id"),
                        "title": t.get("title"),
                        "module": t.get("module"),
                        "filename": t.get("filename"),
                        "tags": t.get("tags", []),
                    }
                    for t in templates
                ]
                formatted = json.dumps(simplified, indent=2, ensure_ascii=False)
                return MCPToolCallResult(
                    content=[
                        MCPToolContent(
                            type="text",
                            text=f"Plantillas corporativas disponibles ({len(simplified)}):\n\n```json\n{formatted}\n```",
                        )
                    ]
                )

            elif name == "funcassist_plan_document_operations":
                prompt = args.get("prompt", "")
                current_doc = args.get("current_document", "")
                section = args.get("section", "Requerimiento Funcional")

                # Formulate structured operations
                ops = [
                    {
                        "operation": "insert_text",
                        "target": {
                            "sectionTitle": section,
                            "position": "inside_end",
                        },
                        "content": f"### Modificación Propuesta\n\n{prompt}",
                    }
                ]
                explanation = (
                    f"Operaciones canónicas planificadas para la sección '{section}':\n\n"
                    f"```json\n{json.dumps(ops, indent=2, ensure_ascii=False)}\n```"
                )
                return MCPToolCallResult(content=[MCPToolContent(type="text", text=explanation)])

            elif name == "funcassist_create_qa_test_plan":
                feat = args.get("feature_name", "Funcionalidad")
                desc = args.get("description", "")
                t_type = args.get("test_type", "regression").capitalize()

                plan_md = (
                    f"# Plan de Pruebas: {feat} ({t_type})\n\n"
                    f"**Descripción del Alcance**: {desc}\n\n"
                    f"| ID | Caso de Prueba | Precondiciones | Pasos | Resultado Esperado | Prioridad |\n"
                    f"|---|---|---|---|---|---|\n"
                    f"| TC-01 | Flujo principal exitoso | Usuario autenticado | 1. Ingresar a {feat}. 2. Ejecutar acción estándar. | Respuesta 200 y confirmación visual. | Alta |\n"
                    f"| TC-02 | Validación de campos requeridos | Campos vacíos | 1. Dejar campos obligatorios vacíos. 2. Intentar guardar. | Mostrar alertas de validación. | Alta |\n"
                    f"| TC-03 | Manejo de errores y límites | Datos fuera de rango | 1. Ingresar valores límites. 2. Enviar petición. | Manejo controlado sin excepciones 500. | Media |\n"
                )
                return MCPToolCallResult(content=[MCPToolContent(type="text", text=plan_md)])

            elif name == "funcassist_summarize_standup":
                yesterday = args.get("yesterday", "")
                today = args.get("today", "")
                blockers = args.get("blockers", "Ninguno")
                proj = args.get("project", "General")

                summary = (
                    f"## 📋 Reporte Daily Standup — Proyecto {proj}\n\n"
                    f"**Ayer**: {yesterday}\n\n"
                    f"**Hoy**: {today}\n\n"
                    f"**Bloqueos / Riesgos**: {blockers}\n"
                )
                return MCPToolCallResult(content=[MCPToolContent(type="text", text=summary)])

            else:
                return MCPToolCallResult(
                    content=[MCPToolContent(type="text", text=f"Herramienta desconocida: {name}")],
                    isError=True,
                )

        except Exception as ex:
            return MCPToolCallResult(
                content=[MCPToolContent(type="text", text=f"Error ejecutando '{name}': {str(ex)}")],
                isError=True,
            )

    async def read_resource(self, uri: str) -> MCPResourceContent:
        """Reads resource content based on URI."""
        if uri == "funcassist://knowledge/index":
            from app.context.retrieval import search_knowledge

            sample = search_knowledge("", top_k=10)
            items = [{"id": s.id, "title": s.title, "source": s.source_label} for s in sample]
            return MCPResourceContent(uri=uri, text=json.dumps(items, indent=2, ensure_ascii=False))

        elif uri == "funcassist://templates/fixtures":
            from app.core.template_storage import list_templates

            templates = list_templates()
            return MCPResourceContent(uri=uri, text=json.dumps(templates, indent=2, ensure_ascii=False))

        return MCPResourceContent(uri=uri, text=f'{{"error": "Resource not found: {uri}"}}')


# Singleton instance of the FuncAssist MCP Server
mcp_server = FuncAssistMCPServer()
