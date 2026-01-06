import pytest
from app import create_app

@pytest.fixture
def app():
    app = create_app('testing')
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_home_page(client):
    """Test that the home page returns a 200 status code."""
    response = client.get('/')
    assert response.status_code == 302 # Redirect to login
