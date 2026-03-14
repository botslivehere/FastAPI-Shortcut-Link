from datetime import datetime, timedelta, timezone
import db as db_module
from sqlalchemy import text

URL = "https://hse.ru/timetable"
URL2 = "https://lms.hse.ru/course"
URL3 = "https://edu.hse.ru/schedule"
ALIAS = "hse"
PROJECT = "hse"
PWD = "pass12345"

async def register_and_login(ac, username, password=PWD):
    await ac.post("/register", json={"username": username, "password": password})
    r = await ac.post("/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

async def shorten(ac, url=URL, headers=None, **kwargs):
    payload = {"original_url": url, **kwargs}
    return await ac.post("/links/shorten", json=payload, headers=headers or {})

# POST /links/shorten

async def test_shorten_anon(client):
    ac, _ = client
    r = await shorten(ac)
    assert r.status_code == 200
    data = r.json()
    assert data["original_url"] == URL
    assert len(data["short_code"]) == 6
    assert data["clicks_count"] == 0
    assert data["expires_at"] is None

async def test_shorten_logined(auth_client):
    ac, _, headers = auth_client
    r = await shorten(ac, headers=headers)
    assert r.status_code == 200

async def test_shorten_alias(client):
    ac, _ = client
    r = await shorten(ac, custom_alias=ALIAS)
    assert r.status_code == 200
    assert r.json()["short_code"] == ALIAS

async def test_shorten_taken_alias(client):
    ac, _ = client
    await shorten(ac, custom_alias=ALIAS)
    r = await shorten(ac, url=URL2, custom_alias=ALIAS)
    assert r.status_code == 400
    assert r.json()["detail"] == "Alias taken"

async def test_shorten_project_expiry(client):
    ac, _ = client
    expires = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)).isoformat()
    r = await shorten(ac, project=PROJECT, expires_at=expires)
    assert r.status_code == 200
    data = r.json()
    assert data["project"] == PROJECT
    assert data["expires_at"] is not None

# GET /links/{short_code}

async def test_redirect_success(client):
    ac, _ = client
    code = (await shorten(ac)).json()["short_code"]
    r = await ac.get(f"/links/{code}")
    assert r.status_code == 307
    assert r.headers["location"] == URL

async def test_redirect_success_redis(client):
    ac, mock = client
    mock.get.return_value = URL2
    code = (await shorten(ac)).json()["short_code"]
    r = await ac.get(f"/links/{code}")
    assert r.status_code == 307
    assert r.headers["location"] == URL2

async def test_redirect_unknown(client):
    ac, _ = client
    r = await ac.get("/links/xxxxxx")
    assert r.status_code == 404

async def test_redirect_expired(client):
    ac, _ = client
    past = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).isoformat()
    code = (await shorten(ac, expires_at=past)).json()["short_code"]
    r = await ac.get(f"/links/{code}")
    assert r.status_code == 410

async def test_redirect_expired_set_redis(client):
    ac, mock = client
    past = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).isoformat()
    code = (await shorten(ac, expires_at=past)).json()["short_code"]
    await ac.get(f"/links/{code}")
    mock.setex.assert_called_once_with(f"link:{code}", 3600, "EXPIRED")

async def test_redirect_expired_get_redis(client):
    ac, mock = client
    mock.get.return_value = "EXPIRED"
    code = (await shorten(ac)).json()["short_code"]
    r = await ac.get(f"/links/{code}")
    assert r.status_code == 410

# GET /links/{short_code}/stats

async def test_stats_correct(client):
    ac, _ = client
    code = (await shorten(ac)).json()["short_code"]
    r = await ac.get(f"/links/{code}/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["original_url"] == URL
    assert data["clicks_count"] == 0
    assert data["last_used_at"] is None

async def test_stats_unknown(client):
    ac, _ = client
    r = await ac.get("/links/xxxxxx/stats")
    assert r.status_code == 404

# GET /links/search

async def test_search_exist(client):
    ac, _ = client
    await shorten(ac, url=URL2)
    r = await ac.get("/links/search", params={"original_url": URL2})
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["original_url"] == URL2

async def test_search_not_exist(client):
    ac, _ = client
    r = await ac.get("/links/search", params={"original_url": "https://unknown.url"})
    assert r.status_code == 200
    assert r.json() == []

async def test_search_exist_multiple(client):
    ac, _ = client
    await shorten(ac, url=URL3, custom_alias="alias1")
    await shorten(ac, url=URL3, custom_alias="alias2")
    r = await ac.get("/links/search", params={"original_url": URL3})
    assert len(r.json()) == 2

# GET /links/expired

async def test_expired_lists(client):
    ac, _ = client
    past = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).isoformat()
    await shorten(ac, url=URL2, expires_at=past)
    r = await ac.get("/links/expired")
    assert r.status_code == 200
    assert any(lnk["original_url"] == URL2 for lnk in r.json())

async def test_expired_lists_excludes_active_links(client):
    ac, _ = client
    future = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)).isoformat()
    await shorten(ac, url=URL2, expires_at=future)
    r = await ac.get("/links/expired")
    assert r.json() == []

# PUT /links/{short_code}

async def test_update_success(auth_client):
    ac, _, headers = auth_client
    code = (await shorten(ac, headers=headers)).json()["short_code"]
    r = await ac.put(f"/links/{code}", json={"new_original_url": URL2}, headers=headers)
    assert r.status_code == 200
    assert r.json()["message"] == "Updated"

async def test_update_success_clears_redis(auth_client):
    ac, mock, headers = auth_client
    code = (await shorten(ac, headers=headers)).json()["short_code"]
    await ac.put(f"/links/{code}", json={"new_original_url": URL2}, headers=headers)
    mock.delete.assert_called_with(f"link:{code}")

async def test_update_token_empty(client):
    ac, _ = client
    code = (await shorten(ac)).json()["short_code"]
    r = await ac.put(f"/links/{code}", json={"new_original_url": URL2})
    assert r.status_code == 401

async def test_update_not_owner(auth_client):
    ac, _, headers = auth_client
    code = (await shorten(ac, headers=headers)).json()["short_code"]
    petrov = await register_and_login(ac, "petrov")
    r = await ac.put(f"/links/{code}", json={"new_original_url": URL2}, headers=petrov)
    assert r.status_code == 403

async def test_update_anon_link(auth_client):
    ac, _, headers = auth_client
    code = (await shorten(ac)).json()["short_code"]
    r = await ac.put(f"/links/{code}", json={"new_original_url": URL2}, headers=headers)
    assert r.status_code == 403

async def test_update_nonexistent_link(auth_client):
    ac, _, headers = auth_client
    r = await ac.put("/links/xxxxxx", json={"new_original_url": URL2}, headers=headers)
    assert r.status_code == 404

# DELETE /links/{short_code}

async def test_delete_success(auth_client):
    ac, _, headers = auth_client
    code = (await shorten(ac, headers=headers)).json()["short_code"]
    r = await ac.delete(f"/links/{code}", headers=headers)
    assert r.status_code == 200
    assert r.json()["message"] == "Deleted"

async def test_delete_token_empty(client):
    ac, _ = client
    code = (await shorten(ac)).json()["short_code"]
    r = await ac.delete(f"/links/{code}")
    assert r.status_code == 401

async def test_delete_not_owner(auth_client):
    ac, _, headers = auth_client
    code = (await shorten(ac, headers=headers)).json()["short_code"]
    sidorov = await register_and_login(ac, "sidorov")
    r = await ac.delete(f"/links/{code}", headers=sidorov)
    assert r.status_code == 403

# GET /projects/{project}/links

async def test_project_correct(client):
    ac, _ = client
    await shorten(ac, url=URL, project=PROJECT)
    r = await ac.get(f"/projects/{PROJECT}/links")
    assert r.status_code == 200
    data = r.json()
    assert data["project"] == PROJECT
    assert len(data["links"]) == 1

async def test_project_unknown(client):
    ac, _ = client
    r = await ac.get("/projects/unknown/links")
    assert r.status_code == 200
    assert r.json()["links"] == []

# DELETE /secret/unused/cleanup

async def test_cleanup_success(client):
    ac, _ = client
    code = (await shorten(ac)).json()["short_code"]
    old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=35)
    async with db_module.engine.begin() as conn:
        await conn.execute(
            text("UPDATE links SET created_at = :t WHERE short_code = :c"),
            {"t": old_time, "c": code},
        )
    r = await ac.delete("/secret/unused/cleanup?days=30")
    assert r.status_code == 200
    assert r.json()["deleted"] == 1

async def test_cleanup_none(client):
    ac, _ = client
    await shorten(ac)
    r = await ac.delete("/secret/unused/cleanup?days=30")
    assert r.status_code == 200
    assert r.json()["deleted"] == 0