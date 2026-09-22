"""Local spending safeguard; delayed billing is not a provider hard cap.
Stops ONLY the configured service, retaining its billed persistent volume.
"""
import json
import math
from pathlib import Path
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'data/hosting-budget.json'


def stop_reason(usage, now, expires):
    if now >= expires:
        return 'time'
    if not isinstance(usage, (float, int)) or not math.isfinite(usage) or usage < 0:
        return 'billing_unavailable'
    return 'budget' if usage >= 3.5 else None


def command(args):
    return subprocess.check_output(['railway', *args], cwd=ROOT, text=True, timeout=45)


def main():
    cfg = json.loads(CONFIG.read_text())
    if cfg.get('stopped'):
        return
    usage = None
    try:
        report = json.loads(command(['usage', 'projects', '--project', cfg['project'], '--workspace', cfg['workspace'], '--json']))
        if report['project']['id'] == cfg['project']:
            usage = report['currentUsageDollars']
    except Exception:
        pass
    reason = stop_reason(usage, time.time(), cfg['expires'])
    if '--check-only' in sys.argv:
        print(json.dumps({'usage':usage, 'stopReason':reason, 'expires':cfg['expires']}))
        return
    if reason:
        command(['down', '--project', cfg['project'], '--service', cfg['service'], '--environment', cfg['environment'], '--yes'])
        cfg.update(stopped=True, reason=reason, lastUsage=usage)
        pending = CONFIG.with_suffix('.tmp')
        pending.write_text(json.dumps(cfg, indent=2))
        pending.replace(CONFIG)
        print(f'TRENCHNET: сервер остановлен защитой бюджета ({reason}). Учтённый расход: {usage} USD. Код и том с базой сохранены; другие проекты не затронуты. Хранение тома может продолжать тарифицироваться. Продление требует согласования.')


if __name__ == '__main__':
    main()
