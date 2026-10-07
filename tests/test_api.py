from datetime import datetime, timedelta, timezone

def create_link(client, url="https://www.python.org"):
    response = client.post("/shorten", json={"url": url})
    assert response.status_code == 201
    return response.json()


def test_create_short_link(client):
    data = create_link(client)
    assert len(data["code"]) == 7
    assert data["original_url"] == "https://www.python.org/"
    assert data["short_url"].endswith(data["code"])


def test_invalid_url_rejected(client):
    response = client.post("/shorten", json={"url": "hello"})
    assert response.status_code == 422


def test_non_http_scheme_rejected(client):
    response = client.post("/shorten", json={"url": "javascript:alert(1)"})
    assert response.status_code == 422


def test_redirect(client):
    data = create_link(client)
    response = client.get(f"/{data['code']}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://www.python.org/"


def test_unknown_code_returns_404(client):
    response = client.get("/doesnotexist", follow_redirects=False)
    assert response.status_code == 404


def test_clicks_are_counted(client):
    data = create_link(client)
    for _ in range(3):
        client.get(f"/{data['code']}", follow_redirects=False)

    stats = client.get(f"/stats/{data['code']}").json()
    assert stats["total_clicks"] == 3
    assert len(stats["clicks_per_day"]) == 1
    assert stats["clicks_per_day"][0]["clicks"] == 3


def test_referrers_are_tracked(client):
    data = create_link(client)
    code = data["code"]
    client.get(f"/{code}", headers={"referer": "https://twitter.com"}, follow_redirects=False)
    client.get(f"/{code}", headers={"referer": "https://twitter.com"}, follow_redirects=False)
    client.get(f"/{code}", headers={"referer": "https://google.com"}, follow_redirects=False)

    stats = client.get(f"/stats/{code}").json()
    assert stats["top_referrers"][0] == {"referrer": "https://twitter.com", "clicks": 2}
    assert stats["top_referrers"][1] == {"referrer": "https://google.com", "clicks": 1}


def test_stats_unknown_code_returns_404(client):
    response = client.get("/stats/doesnotexist")
    assert response.status_code == 404
def test_custom_alias(client):
    response = client.post("/shorten", json={"url": "https://www.python.org", "alias": "my-link"})
    assert response.status_code == 201
    assert response.json()["code"] == "my-link"

    redirect = client.get("/my-link", follow_redirects=False)
    assert redirect.status_code == 307


def test_duplicate_alias_returns_409(client):
    client.post("/shorten", json={"url": "https://www.python.org", "alias": "taken"})
    response = client.post("/shorten", json={"url": "https://fastapi.tiangolo.com", "alias": "taken"})
    assert response.status_code == 409


def test_reserved_alias_returns_409(client):
    response = client.post("/shorten", json={"url": "https://www.python.org", "alias": "docs"})
    assert response.status_code == 409


def test_invalid_alias_rejected(client):
    response = client.post("/shorten", json={"url": "https://www.python.org", "alias": "bad alias!"})
    assert response.status_code == 422


def test_past_expiry_rejected(client):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = client.post("/shorten", json={"url": "https://www.python.org", "expires_at": past})
    assert response.status_code == 422


def test_future_expiry_link_works(client):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    data = client.post("/shorten", json={"url": "https://www.python.org", "expires_at": future}).json()
    assert data["expires_at"] is not None
    assert client.get(f"/{data['code']}", follow_redirects=False).status_code == 307


def test_expired_link_returns_410(client):
    soon = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    data = client.post("/shorten", json={"url": "https://www.python.org", "expires_at": soon}).json()

    import time
    time.sleep(1.5)

    assert client.get(f"/{data['code']}", follow_redirects=False).status_code == 410


def test_delete_link(client):
    data = client.post("/shorten", json={"url": "https://www.python.org"}).json()
    code = data["code"]
    client.get(f"/{code}", follow_redirects=False)  # create a click so we test the cascade

    assert client.delete(f"/links/{code}").status_code == 204
    assert client.get(f"/{code}", follow_redirects=False).status_code == 404


def test_delete_unknown_link_returns_404(client):
    assert client.delete("/links/doesnotexist").status_code == 404