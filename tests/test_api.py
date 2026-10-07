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