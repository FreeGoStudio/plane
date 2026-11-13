# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Export the five tool schemas from the installed official SDK without credentials."""
import asyncio
import json
from gateway import build_server

async def main():
    server = build_server(None, 'https://plane.example.invalid', 'https://plane.example.invalid/mcp')
    tools = await server.list_tools()
    print(json.dumps({'tools': [tool.model_dump(mode='json', exclude_none=True) for tool in tools]}, indent=2))

if __name__ == '__main__':
    asyncio.run(main())
