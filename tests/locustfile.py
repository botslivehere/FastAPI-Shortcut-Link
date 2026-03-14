import random
import string
from locust import HttpUser, between, task

def rnd_url():
    slug = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"https://hse.test/{slug}"

class AnonymousUser(HttpUser):
    wait_time = between(0.5, 1.0)
    short_codes: list[str]

    def on_start(self):
        self.short_codes = []
        for _ in range(5):
            self.make_link()

    def make_link(self):
        r = self.client.post("/links/shorten",
            json={"original_url": rnd_url()}
        )
        if r.status_code == 200:
            self.short_codes.append(r.json()["short_code"])

    @task(5)
    def create_link(self):
        self.make_link()

    @task(10)
    def redirect_link(self):
        if not self.short_codes:
            return
        code = random.choice(self.short_codes)
        self.client.get(f"/links/{code}",
            allow_redirects=False
        )

    @task(2)
    def search_link(self):
        self.client.get("/links/search",
            params={"original_url": rnd_url()}
        )

    @task(2)
    def get_stats(self):
        if not self.short_codes:
            return
        code = random.choice(self.short_codes)
        self.client.get(f"/links/{code}/stats")


class AuthenticatedUser(HttpUser):
    wait_time = between(0.5, 1.0)
    short_codes: list[str]
    headers: dict

    def on_start(self):
        self.short_codes = []
        uid = "".join(random.choices(string.ascii_lowercase, k=10))
        password = "hsetest123"

        self.client.post("/register", json={"username": uid, "password": password})
        r = self.client.post("/login", json={"username": uid, "password": password})
        if r.status_code == 200:
            token = r.json().get("access_token", "")
            self.headers = {"Authorization": f"Bearer {token}"}
        else:
            self.headers = {}

    @task(6)
    def create_link(self):
        r = self.client.post("/links/shorten",
            json={"original_url": rnd_url(), "project": "load-test"},
            headers=self.headers
        )
        if r.status_code == 200:
            self.short_codes.append(r.json()["short_code"])

    @task(8)
    def redirect_link(self):
        if not self.short_codes:
            return
        code = random.choice(self.short_codes)
        self.client.get(f"/links/{code}",
            allow_redirects=False
        )

    @task(2)
    def update_link(self):
        if not self.short_codes:
            return
        code = random.choice(self.short_codes)
        self.client.put(f"/links/{code}",
            json={"new_original_url": rnd_url()},
            headers=self.headers
        )

    @task(1)
    def delete_link(self):
        if not self.short_codes:
            return
        code = self.short_codes.pop()
        self.client.delete(f"/links/{code}",
            headers=self.headers
        )

    @task(2)
    def project_links(self):
        self.client.get("/projects/load-test/links")