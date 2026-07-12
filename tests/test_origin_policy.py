import ast
from pathlib import Path

import pytest

from career_pipeline.origin_policy import OriginPolicyError, normalize_origin, origin_from_url


def test_normalize_origin_canonicalizes_https_host_idna_ipv6_and_port():
    assert normalize_origin("https://JOBS.Example.OR.KR./") == "https://jobs.example.or.kr:443"
    assert normalize_origin("https://jobs.example.or.kr:8443") == "https://jobs.example.or.kr:8443"
    assert normalize_origin("https://bücher.example") == "https://xn--bcher-kva.example:443"
    assert normalize_origin("https://[2001:DB8::1]") == "https://[2001:db8::1]:443"


@pytest.mark.parametrize(
    "value",
    (
        "http://jobs.example.or.kr",
        "https://user:password@jobs.example.or.kr",
        "https://*.example.or.kr",
        "https://jobs.example.or.kr\nX-Test: unsafe",
        "https://jobs.example.or.kr:invalid",
        "https://jobs.example.or.kr/path",
        "https://jobs.example.or.kr/?query=value",
        "https://jobs.example.or.kr/#fragment",
    ),
)
def test_normalize_origin_rejects_non_bare_or_unsafe_values(value):
    with pytest.raises(OriginPolicyError):
        normalize_origin(value)


def test_origin_from_url_discards_path_query_and_fragment():
    assert origin_from_url("https://JOBS.Example.OR.KR./apply?view=1#top") == "https://jobs.example.or.kr:443"


def test_origin_policy_has_no_execution_or_site_dependencies():
    source = Path("career_pipeline/origin_policy.py").read_text(encoding="utf-8")
    imports = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden = {"application_execution", "platform_catalog", "site_intake", "application_package", "__main__"}
    assert not any(name.split(".")[-1] in forbidden for name in imports)
