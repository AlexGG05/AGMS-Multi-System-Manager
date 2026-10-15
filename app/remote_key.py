"""Isolated, resource-bounded SSH key decoder. No logs or file writes."""
import json
import sys
try:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(5,6))
    resource.setrlimit(resource.RLIMIT_AS,(128*1024*1024,128*1024*1024))
except ImportError:
    pass


def main():
    import asyncssh
    try:
        data=json.loads(sys.stdin.buffer.read(65537))
        key=asyncssh.import_private_key(data['private_key'],passphrase=data.get('passphrase') or None)
        output=key.export_private_key('openssh')
        if len(output)>65536:return 2
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 2


if __name__=='__main__':raise SystemExit(main())
