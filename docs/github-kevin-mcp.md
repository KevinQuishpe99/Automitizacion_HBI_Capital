# Commits con MCP `github-kevin`

Este proyecto está configurado para que el agente publique cambios en GitHub **solo** mediante el servidor MCP **`github-kevin`** (cuenta `kevin19925`), no con `git push` ni con el MCP `github`.

## Configuración en Cursor

En `~/.cursor/mcp.json` debe existir:

```json
"github-kevin": {
  "command": "node",
  "args": ["D:/ProyectosClearMinds/MCPs/github-mcp/dist/index.js"],
  "env": {
    "GITHUB_TOKEN": "<PAT_de_kevin19925>"
  }
}
```

## Permisos del token (obligatorio para este repo)

El repositorio `KevinQuishpe99/Automitizacion_HBI_Capital` es **privado**. El PAT necesita:

1. Scope **`repo`** (acceso a repositorios privados).
2. Que la cuenta **kevin19925** sea **colaboradora** del repositorio (Settings → Collaborators en GitHub).

Sin esto, la API devuelve **404** aunque `git push` funcione con otras credenciales del sistema.

Crear o renovar token: https://github.com/settings/tokens

## Herramienta de commit

El MCP expone `create_or_update_file`, que crea un commit en GitHub por cada archivo.

Parámetros típicos:

| Parámetro | Valor |
|-----------|--------|
| `repo` | `KevinQuishpe99/Automitizacion_HBI_Capital` |
| `path` | Ruta del archivo en el repo |
| `content` | Contenido UTF-8 del archivo |
| `message` | Mensaje del commit |
| `branch` | `main` u otra rama |
| `sha` | Obligatorio al **actualizar** (obtener con `get_file_contents`) |

## Regla del agente

La regla persistente está en [`.cursor/rules/github-kevin-commits.mdc`](../.cursor/rules/github-kevin-commits.mdc).

## Comprobar que funciona

En el chat de Cursor:

1. Reiniciar MCP `github-kevin` (Tools & Integrations).
2. Pedir: *"Usa github-kevin get_me y get_repository en Automitizacion_HBI_Capital"*.

Si `get_repository` responde sin 404, el token ya tiene acceso.
