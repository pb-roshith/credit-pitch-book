import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    processes = []
    for mcp_dir in sorted(ROOT.glob('*_mcp')):
        server = mcp_dir / 'server.py'
        if not server.exists():
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
