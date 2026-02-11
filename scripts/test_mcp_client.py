import asyncio
import sys
# mcp.client.sse.sse_client is available based on introspection
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def test_server(name, url, headers=None):
    print(f"\n--- Testing {name} at {url} ---")
    try:
        # Pass headers to sse_client (it uses httpx under the hood)
        async with sse_client(url, headers=headers) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                
                # List tools
                tools = await session.list_tools()
                print(f"✅ Connected! Found {len(tools.tools)} tools:")
                for tool in tools.tools:
                    print(f"   - {tool.name}: {tool.description}")
                
                # Call ping tool
                try:
                    print("\n> Calling 'ping' tool...")
                    result = await session.call_tool("ping", {})
                    # content is a list of TextContent or ImageContent
                    text = result.content[0].text if result.content else "No content"
                    print(f"✅ Ping result: {text}")
                except Exception as e:
                    print(f"❌ Ping failed: {e}")

                # Call query_incidents if name is ITSM Server
                if "ITSM" in name:
                    try:
                        print("\n> Calling 'query_incidents' tool...")
                        result = await session.call_tool("query_incidents", {"limit": 1})
                        text = result.content[0].text if result.content else "No content"
                        # Limit output length
                        print(f"✅ Query result: {text[:200]}...")
                    except Exception as e:
                        print(f"❌ Query failed: {e}")
                    
    except Exception as e:
        print(f"❌ Connection failed: {e}")

async def main():
    # Use service names from docker-compose network
    # Port 3001 = ITSM, 3002 = Automation
    # We must set Host header to localhost to pass FastMCP's host check
    await test_server("ITSM Server", "http://mcp-itsm:3001/sse", headers={"Host": "localhost:3001"})
    await test_server("Automation Server", "http://mcp-automation:3002/sse", headers={"Host": "localhost:3002"})

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
