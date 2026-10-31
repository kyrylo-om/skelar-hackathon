from django.urls import reverse


def test_health(client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_sets_csrf_cookie(client):
    response = client.get(reverse("health"))

    assert "csrftoken" in response.cookies
