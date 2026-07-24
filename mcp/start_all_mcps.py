import subprocess
import sys
import socket
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent


def is_port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.4):
            return True
    except OSError:
        return False


def main():
    processes = []
    for mcp_dir in sorted(ROOT.glob('*_mcp')):
        server = mcp_dir / 'server.py'
        if not server.exists():
            continue
        values = dotenv_values(mcp_dir / '.env')
        port = int(values.get('MCP_PORT', '8010'))
        if is_port_open(port):
            print(f'{mcp_dir.name} is already running on port {port}.')
            continue
        print(f'Starting {mcp_dir.name}...')
        processes.append(
            subprocess.Popen(
                [sys.executable, 'server.py'],
                cwd=mcp_dir,
            )
        )

    if not processes:
        print('No MCP folders found under mcp/.')
        return

    print(f'Started {len(processes)} MCP server(s). Press Ctrl+C to stop.')
    try:
        for process in processes:
            process.wait()
    except KeyboardInterrupt:
        for process in processes:
            process.terminate()


if __name__ == '__main__':
    main()
