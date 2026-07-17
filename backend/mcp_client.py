from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def list_mcp_tools(mcp_url):
    async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    'name': tool.name,
                    'description': tool.description or '',
                    'inputSchema': tool.inputSchema,
                }
                for tool in result.tools
            ]


async def call_mcp_tool(mcp_url, tool_name, arguments=None):
    async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments or {})
            return result.model_dump(mode='json')
