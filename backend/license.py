import hashlib
import base64
import platform
import subprocess
import os
import sys
import re
import json
from pathlib import Path

_KEY_SEED_PARTS = [
    "DyLnWebF",
    "DYuYinLi",
    "etcher@20",
    "24!Priv#K"
]

_CONFIG_DIR = Path.home() / ".douyin_live_fetcher"
_LICENSE_FILE = _CONFIG_DIR / "license.bin"


def _get_key():
    seed = ''.join(_KEY_SEED_PARTS).encode('utf-8')
    key_material = hashlib.pbkdf2_hmac('sha256', seed, b'dyfetcher_secure_salt_2024', 200000)
    return base64.urlsafe_b64encode(key_material[:32])


def _run_cmd(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except Exception:
        return ''


def _collect_hardware_info():
    info = {}
    system = platform.system()

    if system == 'Windows':
        cpu_id = _run_cmd(['wmic', 'cpu', 'get', 'processorid', '/format:csv'])
        board_serial = _run_cmd(['wmic', 'baseboard', 'get', 'serialnumber', '/format:csv'])
        disk_serial = _run_cmd(['wmic', 'diskdrive', 'get', 'serialnumber', '/format:csv'])
        mac = _run_cmd(['wmic', 'nic', 'where', 'NetEnabled=true', 'get', 'MACAddress', '/format:csv'])

        for line in cpu_id.split('\n'):
            parts = line.strip().split(',')
            if len(parts) >= 2 and parts[-1] and parts[-1] != 'ProcessorId':
                info['cpu'] = parts[-1].strip()
                break

        for line in board_serial.split('\n'):
            parts = line.strip().split(',')
            if len(parts) >= 2 and parts[-1] and parts[-1] != 'SerialNumber':
                info['board'] = parts[-1].strip()
                break

        for line in disk_serial.split('\n'):
            parts = line.strip().split(',')
            if len(parts) >= 2 and parts[-1] and parts[-1] != 'SerialNumber':
                info['disk'] = parts[-1].strip()
                break

        for line in mac.split('\n'):
            parts = line.strip().split(',')
            if len(parts) >= 2 and parts[-1] and parts[-1] != 'MACAddress':
                info['mac'] = parts[-1].strip().replace(':', '').upper()
                break

    elif system == 'Linux':
        try:
            with open('/proc/cpuinfo') as f:
                content = f.read()
                for line in content.split('\n'):
                    if line.startswith('serial'):
                        info['cpu'] = line.split(':')[1].strip()
                        break
                if not info.get('cpu'):
                    for line in content.split('\n'):
                        if 'model name' in line.lower():
                            info['cpu'] = line.split(':')[1].strip()
                            break
        except Exception:
            pass

        board = _run_cmd(['dmidecode', '-s', 'system-serial-number'])
        if board and 'Permission denied' not in board:
            info['board'] = board.strip()

        if not info.get('board'):
            try:
                board_paths = [
                    '/sys/class/dmi/id/board_serial',
                    '/sys/class/dmi/id/product_uuid',
                    '/sys/class/dmi/id/product_serial',
                    '/sys/class/dmi/id/machine_id'
                ]
                for p in board_paths:
                    if os.path.exists(p):
                        with open(p) as f:
                            val = f.read().strip()
                            if val and val not in ('To be filled by O.E.M.', 'Default string'):
                                info['board'] = val
                                break
            except Exception:
                pass

        disk = _run_cmd(['lsblk', '-dno', 'SERIAL'])
        if disk:
            for line in disk.split('\n'):
                val = line.strip()
                if val:
                    info['disk'] = val
                    break

        if not info.get('disk'):
            try:
                disk_paths = [
                    '/sys/block/sda/serial',
                    '/sys/block/nvme0n1/serial',
                    '/sys/block/vda/serial',
                    '/sys/block/sdb/serial',
                    '/sys/block/nvme1n1/serial'
                ]
                for p in disk_paths:
                    if os.path.exists(p):
                        with open(p) as f:
                            val = f.read().strip()
                            if val:
                                info['disk'] = val
                                break
            except Exception:
                pass

        try:
            for iface in sorted(os.listdir('/sys/class/net/')):
                if iface == 'lo':
                    continue
                with open(f'/sys/class/net/{iface}/address') as f:
                    mac = f.read().strip().replace(':', '').upper()
                    if mac and mac != '00:00:00:00:00:00'.replace(':', '').upper():
                        info['mac'] = mac
                        break
        except Exception:
            pass

    elif system == 'Darwin':
        hardware = _run_cmd(['system_profiler', 'SPHardwareDataType'])
        for line in hardware.split('\n'):
            if 'Serial Number' in line or 'Hardware UUID' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    val = parts[-1].strip()
                    if val:
                        info['cpu'] = val
                        break

        disk_info = _run_cmd(['diskutil', 'info', '/'])
        for line in disk_info.split('\n'):
            if 'Serial Number' in line or 'Device UUID' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    val = parts[-1].strip()
                    if val:
                        info['disk'] = val
                        break

        mac = _run_cmd(['networksetup', '-getmacaddress', 'en0'])
        m = re.search(r'([0-9A-Fa-f:]{17})', mac)
        if m:
            info['mac'] = m.group(1).replace(':', '').upper()

    if not info.get('cpu'):
        info['cpu'] = platform.processor() or platform.machine()
    if not info.get('mac'):
        try:
            import uuid
            mac_int = uuid.getnode()
            if mac_int:
                info['mac'] = '{:012X}'.format(mac_int)
        except Exception:
            info['mac'] = 'N/A'
    if not info.get('board'):
        info['board'] = 'N/A'
    if not info.get('disk'):
        info['disk'] = 'N/A'

    return info


def get_machine_code():
    info = _collect_hardware_info()
    raw = f"{info.get('cpu', '')}|{info.get('board', '')}|{info.get('disk', '')}|{info.get('mac', '')}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest().upper()


def get_hardware_summary():
    info = _collect_hardware_info()
    return {
        'cpu': info.get('cpu', 'N/A')[:20],
        'board': info.get('board', 'N/A')[:20],
        'disk': info.get('disk', 'N/A')[:20],
        'mac': info.get('mac', 'N/A'),
        'os': f"{platform.system()} {platform.release()}"
    }


def encrypt_machine_code(machine_code):
    try:
        from cryptography.fernet import Fernet
        key = _get_key()
        f = Fernet(key)
        token = f.encrypt(machine_code.encode('utf-8'))
        return token.decode('utf-8')
    except ImportError:
        raise RuntimeError("缺少 cryptography 库，请执行: pip install cryptography")
    except Exception as e:
        raise RuntimeError(f"加密失败: {e}")


def verify_license(license_key):
    try:
        from cryptography.fernet import Fernet, InvalidToken
        key = _get_key()
        f = Fernet(key)
        decrypted = f.decrypt(license_key.encode('utf-8')).decode('utf-8')
        current_code = get_machine_code()
        return decrypted.strip().upper() == current_code
    except ImportError:
        raise RuntimeError("缺少 cryptography 库，请执行: pip install cryptography")
    except InvalidToken:
        return False
    except Exception as e:
        return False


def save_license(license_key):
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        'license_key': license_key,
        'machine_code': get_machine_code(),
        'verified_at': __import__('datetime').datetime.now().isoformat()
    }
    with open(_LICENSE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def clear_license():
    if _LICENSE_FILE.exists():
        _LICENSE_FILE.unlink()


def check_license_status():
    if not _LICENSE_FILE.exists():
        return {'verified': False, 'machine_code': get_machine_code(), 'hardware': get_hardware_summary()}

    try:
        with open(_LICENSE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        license_key = data.get('license_key', '')
        if not license_key:
            return {'verified': False, 'machine_code': get_machine_code(), 'hardware': get_hardware_summary()}

        ok = verify_license(license_key)
        return {
            'verified': ok,
            'machine_code': get_machine_code(),
            'hardware': get_hardware_summary() if not ok else None,
            'verified_at': data.get('verified_at', '')
        }
    except Exception:
        return {'verified': False, 'machine_code': get_machine_code(), 'hardware': get_hardware_summary()}
