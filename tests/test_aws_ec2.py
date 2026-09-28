from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from typer.testing import CliRunner


MODULE_PATH = Path(__file__).parents[1] / "scripts/aws/aws-ec2.py"
SPEC = importlib.util.spec_from_file_location("aws_ec2", MODULE_PATH)
assert SPEC and SPEC.loader
aws_ec2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aws_ec2)

runner = CliRunner()


def instance(**overrides: object) -> dict:
    value = {
        "InstanceId": "i-0123456789abcdef0",
        "State": {"Name": "running"},
        "InstanceType": "t3.small",
        "PlatformDetails": "Linux/UNIX",
        "Architecture": "x86_64",
        "ImageId": "ami-0123456789abcdef0",
        "Placement": {"AvailabilityZone": "us-east-1a"},
        "KeyName": "prod-web",
        "IamInstanceProfile": {
            "Arn": "arn:aws:iam::123456789012:instance-profile/WebInstanceRole"
        },
        "PrivateIpAddress": "10.0.12.34",
        "PrivateDnsName": "ip-10-0-12-34.ec2.internal",
        "PublicIpAddress": "203.0.113.42",
        "VpcId": "vpc-0123456789abcdef0",
        "SubnetId": "subnet-0123456789abcdef0",
        "SecurityGroups": [{"GroupId": "sg-0123456789abcdef0", "GroupName": "web"}],
        "LaunchTime": datetime(2026, 9, 27, 14, 32, 11, tzinfo=UTC),
        "Tags": [{"Key": "Name", "Value": "web-01"}, {"Key": "Environment", "Value": "prod"}],
    }
    value.update(overrides)
    return value


class FakePaginator:
    def __init__(self, records: list[dict], error: Exception | None = None) -> None:
        self.records = records
        self.error = error
        self.filters: list[dict] | None = None

    def paginate(self, **kwargs: object):
        if self.error:
            raise self.error
        self.filters = kwargs.get("Filters")  # type: ignore[assignment]
        yield {"Reservations": [{"Instances": self.records}]}


class FakeClient:
    def __init__(self, records: list[dict], error: Exception | None = None) -> None:
        self.records = records
        self.error = error
        self.paginator = FakePaginator(records, error)

    def get_paginator(self, name: str) -> FakePaginator:
        assert name == "describe_instances"
        return self.paginator

    def describe_instances(self, **kwargs: object) -> dict:
        if self.error:
            raise self.error
        if "InstanceIds" in kwargs:
            records = [record for record in self.records if record["InstanceId"] in kwargs["InstanceIds"]]
        else:
            records = self.records
        return {"Reservations": [{"Instances": records}]}


def invoke(monkeypatch: pytest.MonkeyPatch, client: FakeClient, *args: str):
    monkeypatch.setattr(aws_ec2, "create_ec2_client", lambda profile, region: client)
    return runner.invoke(
        aws_ec2.app,
        ["--profile", "test", "--region", "us-east-1", *args],
    )


def test_normalized_instance_complete_and_utc() -> None:
    normalized = aws_ec2.normalized_instance(instance())

    assert normalized == {
        "instance_id": "i-0123456789abcdef0",
        "name": "web-01",
        "state": "running",
        "instance_type": "t3.small",
        "os": "Linux/UNIX",
        "architecture": "x86_64",
        "image_id": "ami-0123456789abcdef0",
        "availability_zone": "us-east-1a",
        "key_name": "prod-web",
        "iam_role": "WebInstanceRole",
        "private_ip": "10.0.12.34",
        "private_dns_name": "ip-10-0-12-34.ec2.internal",
        "public_ip": "203.0.113.42",
        "vpc_id": "vpc-0123456789abcdef0",
        "subnet_id": "subnet-0123456789abcdef0",
        "security_groups": [{"id": "sg-0123456789abcdef0", "name": "web"}],
        "launch_time": "2026-09-27T14:32:11Z",
        "tags": {"Name": "web-01", "Environment": "prod"},
    }


def test_normalized_instance_optional_fields_and_empty_collections() -> None:
    normalized = aws_ec2.normalized_instance(
        instance(
            State={"Name": "stopped"},
            Tags=[],
            SecurityGroups=[],
            PlatformDetails=None,
            Platform=None,
            KeyName=None,
            IamInstanceProfile=None,
            PublicIpAddress=None,
        )
    )

    assert normalized["state"] == "stopped"
    assert normalized["name"] is None
    assert normalized["os"] is None
    assert normalized["key_name"] is None
    assert normalized["iam_role"] is None
    assert normalized["public_ip"] is None
    assert normalized["security_groups"] == []
    assert normalized["tags"] == {}


def test_list_json_is_array_with_trailing_newline_and_no_rich_output(monkeypatch: pytest.MonkeyPatch) -> None:
    result = invoke(monkeypatch, FakeClient([instance()]), "list", "--json")

    assert result.exit_code == 0
    assert result.stdout.endswith("\n")
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, list)
    assert parsed[0]["instance_id"] == "i-0123456789abcdef0"
    assert "Fetching instances" not in result.stdout
    assert "No instances found" not in result.stdout
    assert "\x1b" not in result.stdout
    assert result.stderr == ""


def test_list_json_empty_is_empty_array_and_success(monkeypatch: pytest.MonkeyPatch) -> None:
    result = invoke(monkeypatch, FakeClient([]), "list", "--json")

    assert result.exit_code == 0
    assert result.stdout == "[]\n"
    assert result.stderr == ""


@pytest.mark.parametrize("target", ["i-0123456789abcdef0", "web-01"])
def test_describe_json_returns_one_object(monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    result = invoke(monkeypatch, FakeClient([instance()]), "describe", target, "--json")

    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, dict)
    assert parsed["name"] == "web-01"
    assert result.stderr == ""


def test_describe_json_no_match_is_stderr_only(monkeypatch: pytest.MonkeyPatch) -> None:
    result = invoke(monkeypatch, FakeClient([]), "describe", "missing", "--json")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "No instances found" in result.stderr


def test_describe_json_ambiguous_name_is_stderr_only(monkeypatch: pytest.MonkeyPatch) -> None:
    first = instance()
    second = instance(InstanceId="i-abcdef0123456789a")
    result = invoke(monkeypatch, FakeClient([first, second]), "describe", "web", "--json")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Multiple matches" in result.stderr


def test_provider_failure_is_stderr_only(monkeypatch: pytest.MonkeyPatch) -> None:
    error = ClientError({"Error": {"Code": "UnauthorizedOperation", "Message": "denied"}}, "DescribeInstances")
    result = invoke(monkeypatch, FakeClient([], error=error), "list", "--json")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "EC2 lookup failed" in result.stderr


def test_legacy_describe_formats_remain_provider_shaped(monkeypatch: pytest.MonkeyPatch) -> None:
    json_result = invoke(monkeypatch, FakeClient([instance()]), "describe", "web", "--format", "json")
    yaml_result = invoke(monkeypatch, FakeClient([instance()]), "describe", "web", "--format", "yaml")

    assert json_result.exit_code == 0
    assert json.loads(json_result.stdout)["InstanceId"] == "i-0123456789abcdef0"
    assert "instance_id" not in json.loads(json_result.stdout)
    assert yaml_result.exit_code == 0
    assert "InstanceId:" in yaml_result.stdout
    assert "instance_id:" not in yaml_result.stdout


def test_json_and_legacy_format_cannot_be_combined(monkeypatch: pytest.MonkeyPatch) -> None:
    result = invoke(
        monkeypatch,
        FakeClient([instance()]),
        "describe",
        "web",
        "--json",
        "--format",
        "yaml",
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "cannot be combined" in result.stderr
