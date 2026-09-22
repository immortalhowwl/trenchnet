"""Prepare mounted storage, then serve as an unprivileged application user."""
import os
from pathlib import Path


def main():
    directory = Path(os.environ.get('DB_PATH', '/app/data/trenchnet.sqlite')).parent
    directory.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        os.chown(directory, 10001, 10001)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    from server import main as serve
    serve()


if __name__ == '__main__':
    main()
