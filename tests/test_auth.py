USER = "test"
PWD = "test12"

async def test_register_success(client):
    ac, _ = client
    r = await ac.post("/register", json={"username": USER, "password": PWD})
    assert r.status_code == 200
    assert r.json() == {"message": "Registered"}

async def test_register_duplicate_username(client):
    ac, _ = client
    await ac.post("/register", json={"username": USER, "password": PWD})
    r = await ac.post("/register", json={"username": USER, "password": PWD})
    assert r.status_code == 400
    assert r.json()["detail"] == "Username taken"

async def test_register_short_username(client):
    ac, _ = client
    r = await ac.post("/register", json={"username": "ab", "password": PWD})
    assert r.status_code == 422

async def test_register_short_password(client):
    ac, _ = client
    r = await ac.post("/register", json={"username": USER, "password": "123"})
    assert r.status_code == 422

async def test_login_success(client):
    ac, _ = client
    await ac.post("/register", json={"username": USER, "password": PWD})
    r = await ac.post("/login", json={"username": USER, "password": PWD})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"

async def test_login_wrong_password(client):
    ac, _ = client
    await ac.post("/register", json={"username": USER, "password": PWD})
    r = await ac.post("/login", json={"username": USER, "password": "wrong1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Bad credentials"

async def test_login_wrong_user(client):
    ac, _ = client
    r = await ac.post("/login", json={"username": "someuser", "password": PWD})
    assert r.status_code == 401