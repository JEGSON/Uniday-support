"""Generate independent local demo secrets once; never overwrite existing files."""
import base64
import json
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONGO = ROOT / '.env.deploy.mongo'
APP = ROOT / '.env.deploy.app'
IMPORTER = ROOT / '.env.deploy.importer'


def write_new(path, values):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        for name, value in values.items():
            stream.write(f'{name}={value}\n')


def main():
    if any(path.exists() for path in (MONGO, APP, IMPORTER)):
        raise SystemExit('Deployment environment already exists; refusing to overwrite secrets.')
    names = ('AUTH_APP', 'REGISTRY_APP', 'REGISTRY_IMPORTER', 'CASES_APP',
             'STATS_READER', 'AUDIT_APP', 'AUDIT_READER')
    passwords = {name: secrets.token_hex(32) for name in names}
    mongo = {'MONGO_INITDB_ROOT_USERNAME': 'stage7_operator',
             'MONGO_INITDB_ROOT_PASSWORD': secrets.token_hex(32)}
    mongo.update({name + '_PASSWORD': value for name, value in passwords.items()})

    def uri(user, key, database):
        return f'mongodb://{user}:{passwords[key]}@mongodb:27017/?authSource={database}'

    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii')
    app = {'APP_ENV': 'production', 'TRUST_PROXY': '1',
           'SECRET_KEY': secrets.token_hex(32), 'BASE_URL': 'https://localhost:5443',
           'SMTP_HOST': 'mailpit', 'CASE_ACTIVE_KEY_ID': 'stage7-v1',
           'CASE_ENCRYPTION_KEYS': "'" + json.dumps({'stage7-v1': key}, separators=(',', ':')) + "'",
           'MONGODB_URI': uri('auth_app', 'AUTH_APP', 'auth_db'),
           'REGISTRY_URI': uri('registry_app', 'REGISTRY_APP', 'registry_db'),
           'CASES_URI': uri('cases_app', 'CASES_APP', 'cases_db'),
           'STATS_URI': uri('stats_reader', 'STATS_READER', 'cases_db'),
           'MONGO_AUDIT_WRITE_URI': uri('audit_app', 'AUDIT_APP', 'audit_db'),
           'MONGO_AUDIT_READ_URI': uri('audit_reader', 'AUDIT_READER', 'audit_db')}
    write_new(MONGO, mongo)
    write_new(APP, app)
    write_new(IMPORTER, {'REGISTRY_SEED_URI': uri('registry_importer', 'REGISTRY_IMPORTER', 'registry_db')})
    print('Created independent, owner-only deployment environment files. Back up the encryption key separately.')


if __name__ == '__main__':
    main()
