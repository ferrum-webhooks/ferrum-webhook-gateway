import pytest

from app import ssrf


@pytest.fixture(autouse=True)
def strict(monkeypatch):
    monkeypatch.setattr(ssrf, "ALLOW_PRIVATE", False)
    monkeypatch.setattr(ssrf, "ALLOWED_SCHEMES", ("https", "http"))


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",   # cloud metadata
    "http://127.0.0.1:6379/",                      # local redis
    "http://[::1]/",
    "http://10.0.0.5/", "http://172.16.0.1/", "http://192.168.1.1/",
    "http://100.64.0.1/",                          # CGNAT / shared address space
    "http://0.0.0.0/",
    "http://[::ffff:127.0.0.1]/",                  # IPv4-mapped IPv6 loopback
    "http://localhost/", "http://redis.ferrum.svc.cluster.local/", "http://postgres.svc/",
    "http://foo.internal/", "ftp://example.com/", "file:///etc/passwd",
    "https://user:pw@example.com/",
])
def test_blocked(url):
    with pytest.raises(ssrf.BlockedTarget):
        ssrf.check_url(url, resolve_dns=False)


def test_public_literal_allowed():
    ssrf.check_url("https://93.184.216.34/hook", resolve_dns=False)


def test_hostname_resolving_to_private_is_blocked(monkeypatch):
    import ipaddress
    monkeypatch.setattr(ssrf, "resolve", lambda h, p: [ipaddress.ip_address("10.1.2.3")])
    with pytest.raises(ssrf.BlockedTarget):
        ssrf.check_url("https://rebind.attacker.example/hook")


def test_unresolvable_host_is_accepted(monkeypatch):
    import socket
    def boom(h, p): raise socket.gaierror("nope")
    monkeypatch.setattr(ssrf, "resolve", boom)
    ssrf.check_url("https://not-yet-created.example/hook")   # fails later as a normal delivery error


def test_api_rejects_private_target(client, auth, monkeypatch):
    monkeypatch.setattr(ssrf, "ALLOW_PRIVATE", False)
    r = client.post("/webhooks", json={"url": "http://169.254.169.254/x", "event_type": "t"}, headers=auth)
    assert r.status_code == 422 and "rejected" in r.json()["detail"]
    ok = client.post("/webhooks", json={"url": "https://93.184.216.34/x", "event_type": "t"}, headers=auth)
    assert ok.status_code == 201
    r = client.patch(f"/webhooks/{ok.json()['id']}", json={"url": "http://10.0.0.1/"}, headers=auth)
    assert r.status_code == 422
