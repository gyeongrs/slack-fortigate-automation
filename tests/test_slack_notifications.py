from slack_bot.metadata import (
    check_logtraffic,
    decode_meta,
    encode_meta,
    extract_policies_yaml,
    logtraffic_summary,
)
from slack_bot.pr_audit import parse_apply_log


def test_encode_decode_meta_roundtrip():
    data = {
        "requester": "alice",
        "requester_slack_id": "U123",
        "justification": "NETOPS-1",
        "policy_name": "allow-web",
        "policies": [{"name": "p1", "logtraffic": "all"}],
    }
    body = f"Hello\n\n{encode_meta(data)}\n"
    assert decode_meta(body) == data


def test_check_logtraffic_ok():
    policies = [{"name": "a", "logtraffic": "all"}, {"name": "b", "logtraffic": "all"}]
    ok, issues = check_logtraffic(policies)
    assert ok
    assert issues == []


def test_check_logtraffic_missing():
    policies = [{"name": "a", "logtraffic": "disable"}]
    ok, issues = check_logtraffic(policies)
    assert not ok
    assert "a" in issues[0]


def test_logtraffic_summary_all_enabled():
    text = logtraffic_summary([{"name": "p", "logtraffic": "all"}])
    assert "white_check_mark" in text
    assert "logtraffic: all" in text


def test_validate_result_blocks_success():
    from slack_bot.messages import validate_result_blocks

    blocks = validate_result_blocks(
        {
            "status": "success",
            "policy_name": "allow-web",
            "pr_number": 42,
            "pr_url": "https://github.com/org/repo/pull/42",
            "requester": "alice",
            "requester_slack_id": "U1",
            "justification": "NETOPS-1",
            "policies": [{"name": "p", "logtraffic": "all"}],
            "validate_log": "Validation passed.",
            "plan_log": "Plan: 1 to create",
            "workflow_url": "https://github.com/org/repo/actions/runs/1",
        }
    )
    text = str(blocks)
    assert "PR validation passed" in text
    assert "CODEOWNERS" in text
    assert "allow-web" in text


def test_validate_result_blocks_failure():
    from slack_bot.messages import validate_result_blocks

    blocks = validate_result_blocks(
        {
            "status": "failure",
            "policy_name": "bad",
            "validate_log": "Validation failed: any-any",
        }
    )
    assert "FAILED" in str(blocks)


def test_request_summary_layout():
    from slack_bot.messages import request_summary_blocks

    blocks = request_summary_blocks(
        policy_name="Test",
        requester_id="U1",
        requester_name="gyeongrs",
        requester_real_name="songyeongrak",
        team_name="myteam",
        justification="test",
        pr={"url": "https://github.com/o/r/pull/22", "number": 22},
        policies=[
            {
                "name": "D1CR10.56.10.1>D1CR10.57.10.1",
                "device": "dc1-core-fw",
                "srcaddr": ["Azure-10.56.10.1"],
                "dstaddr": ["auto-10.57.10.1"],
                "service": ["HTTPS"],
                "logtraffic": "all",
                "expires_at": "2026-06-17",
            }
        ],
        targets=[
            {"device": "dc1-core-fw", "srcintf": "core-trust", "dstintf": "core-untrust"},
        ],
        expires_at="2026-06-17",
    )
    text = blocks[0]["text"]["text"]
    assert "*PR:*" in text
    assert "songyeongrak (gyeongrs) (myteam)" in text
    assert "*Commnets:*" in text
    assert "D1CR10.56.10.1>D1CR10.57.10.1 (dc1-core-fw)" in text
    assert "Azure-10.56.10.1>auto-10.57.10.1 | HTTPS" in text
    assert "log: all | until 2026-06-17" in text
    assert "*Target FW*" in text
    assert "srcintf core-trust, dstintf core-untrust" in text


def test_extract_policies_yaml_from_pr_body():
    body = (
        "**Per-firewall policies:**\n```yaml\n"
        "policies:\n"
        "- name: test\n"
        "  logtraffic: all\n"
        "```\n"
    )
    policies = extract_policies_yaml(body)
    assert len(policies) == 1
    assert policies[0]["name"] == "test"


def test_parse_apply_log():
    log = """
Validation passed.
[inet-fw] applying 2 change(s)
[inet-fw] [created] policy 'allow-web'
[inet-fw] [ERROR] policy 'bad': HTTP 403
"""
    lines = parse_apply_log(log)
    assert any("[created]" in line for line in lines)
    assert any("[ERROR]" in line for line in lines)
