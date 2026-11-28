import stat

import pytest
from dotenv import dotenv_values

from scripts import prepare_deployment


def test_deployment_secrets_are_separate_and_not_overwritten(tmp_path, monkeypatch, capsys):
    mongo = tmp_path / 'mongo.env'
    app = tmp_path / 'app.env'
    importer = tmp_path / 'importer.env'
    monkeypatch.setattr(prepare_deployment, 'MONGO', mongo)
    monkeypatch.setattr(prepare_deployment, 'APP', app)
    monkeypatch.setattr(prepare_deployment, 'IMPORTER', importer)
    prepare_deployment.main()
    env = dotenv_values(app)
    root_env = dotenv_values(mongo)
    importer_env = dotenv_values(importer)
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in (mongo, app, importer))
    assert 'REGISTRY_SEED_URI' not in env and 'REGISTRY_SEED_URI' in importer_env
    assert root_env['MONGO_INITDB_ROOT_PASSWORD'] not in repr(env)
    assert root_env['MONGO_INITDB_ROOT_PASSWORD'] not in capsys.readouterr().out
    original = app.read_bytes()
    with pytest.raises(SystemExit):
        prepare_deployment.main()
    assert app.read_bytes() == original
