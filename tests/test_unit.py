import string
from datetime import datetime, timezone
import pytest
from jose import jwt
from pydantic import ValidationError
from auth import check_pw, get_hash_pw, make_token
from links import create_random_url_prefix
from schemas import LinkCreate, LinkOut, UserAuth

SECRET = "test-secret-12345"

# default alias generation

def test_prefix():
    assert len(create_random_url_prefix()) == 6

def test_prefix_charset():
    valid = set(string.ascii_letters + string.digits)
    assert all(c in valid for c in create_random_url_prefix())

def test_prefix_uniqueness():
    codes = {create_random_url_prefix() for _ in range(100)}
    assert len(codes) >= 95

# password hashing

def test_hash_pass():
    pw = "mypassword"
    assert check_pw(pw, get_hash_pw(pw))

def test_hash_fail():
    assert not check_pw("wrong", get_hash_pw("correct"))

def test_hash_uniqueness():
    pw = "same"
    assert get_hash_pw(pw) != get_hash_pw(pw)

# JWT token

def test_token_creation():
    token = make_token("ivan")
    payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert payload["sub"] == "ivan"

def test_token_expiry():
    token = make_token("ivan")
    payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert "exp" in payload
    assert payload["exp"] > datetime.now(timezone.utc).timestamp()

# schema validation

def test_user_schema_short_username():
    with pytest.raises(ValidationError):
        UserAuth(username="ab", password="validpass")

def test_user_schema_short_password():
    with pytest.raises(ValidationError):
        UserAuth(username="ivan", password="123")

def test_link_create_defaults():
    lc = LinkCreate(original_url="https://hse.ru")
    assert lc.custom_alias is None
    assert lc.expires_at is None
    assert lc.project is None

def test_link_out_model_validation():
    class FakeLink:
        short_code = "abc123"
        original_url = "https://hse.ru"
        created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = None
        project = None
        clicks_count = 0

    lo = LinkOut.model_validate(FakeLink())
    assert lo.short_code == "abc123"
    assert lo.clicks_count == 0