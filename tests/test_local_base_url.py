from unittest.mock import patch

from app import create_app


def test_default_link_origin_uses_ipv4_loopback():
    with patch.dict('os.environ', {'BASE_URL': ''}), patch('app.dotenv_values', return_value={}), patch('db.init_app'):
        app = create_app()
    assert app.config['BASE_URL'] == 'http://127.0.0.1:5000'
