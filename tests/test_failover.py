import pytest
import time
import requests
import dns.resolver
import os
import boto3

LOCALSTACK_ENDPOINT_URL = os.environ.get(
    "LOCALSTACK_ENDPOINT_URL", "http://localhost:4566"
)
CHAOS_ENDPOINT = f"{LOCALSTACK_ENDPOINT_URL}/_localstack/chaos/faults"

HOSTED_ZONE_NAME = "hello-localstack.com"
PRIMARY_API_ID = "12345"
SECONDARY_API_ID = "67890"
PRIMARY_API_REGION = "us-east-1"
HEALTH_CHECK_RESOURCE_REGION = "us-west-1"
HEALTH_CHECK_PORT = 4566
HEALTH_CHECK_RESOURCE_PATH = "/dev/healthcheck"

PRIMARY_API_GATEWAY_FQDN = f"{PRIMARY_API_ID}.execute-api.localhost.localstack.cloud"
SECONDARY_API_GATEWAY_FQDN = (
    f"{SECONDARY_API_ID}.execute-api.localhost.localstack.cloud"
)
FAILOVER_RECORD_NAME = f"test.{HOSTED_ZONE_NAME}"

HEALTH_CHECK_INTERVAL = 10
HEALTH_CHECK_FAILURE_THRESHOLD = 2
INITIAL_DNS_WAIT_PERIOD = 10
DNS_CHECK_RETRIES = 4
DNS_CHECK_DELAY = 5
FAILOVER_REACTION_WAIT = (HEALTH_CHECK_INTERVAL * HEALTH_CHECK_FAILURE_THRESHOLD) + 25


def get_cname_target(hostname, dns_server="127.0.0.1", port=53, max_cname_hops=5):
    resolver = dns.resolver.Resolver()
    resolver.nameservers = [dns_server]
    resolver.port = port
    resolver.timeout = 2
    resolver.lifetime = 5

    current_hostname = hostname

    for hop in range(max_cname_hops):
        if ".execute-api.localhost.localstack.cloud" in current_hostname:
            return current_hostname

        try:
            answers = resolver.resolve(current_hostname, "CNAME")
            if answers and len(answers) > 0:
                new_target = str(answers[0].target).rstrip(".")
                if not new_target or new_target == current_hostname:
                    return current_hostname
                current_hostname = new_target
                if ".execute-api.localhost.localstack.cloud" in current_hostname:
                    return current_hostname
            else:
                return current_hostname
        except dns.resolver.NoAnswer:
            return current_hostname
        except dns.resolver.NXDOMAIN:
            return "NXDOMAIN"
        except dns.exception.Timeout:
            return "TIMEOUT"
        except Exception as e:
            return f"ERROR_RESOLVING"
    return current_hostname


@pytest.fixture(scope="session")
def route53_client():
    return boto3.client(
        "route53",
        endpoint_url=LOCALSTACK_ENDPOINT_URL,
        region_name=HEALTH_CHECK_RESOURCE_REGION,
    )


@pytest.fixture(scope="session")
def health_check_id(route53_client):
    try:
        paginator = route53_client.get_paginator("list_health_checks")
        for page in paginator.paginate():
            for hc in page.get("HealthChecks", []):
                config = hc.get("HealthCheckConfig", {})
                if (
                    config.get("FullyQualifiedDomainName") == PRIMARY_API_GATEWAY_FQDN
                    and config.get("Port") == HEALTH_CHECK_PORT
                    and config.get("ResourcePath") == HEALTH_CHECK_RESOURCE_PATH
                ):
                    found_id = hc["Id"]
                    return found_id
        pytest.fail(
            f"Could not find an existing health check for {PRIMARY_API_GATEWAY_FQDN}:{HEALTH_CHECK_PORT}{HEALTH_CHECK_RESOURCE_PATH}"
        )
    except Exception as e:
        pytest.fail(f"Error trying to find health check ID: {e}")
    return None


def perform_dns_check_with_retry(fqdn_to_check, expected_target_fqdn, step_name):
    print(f"\n{step_name} (expecting: {expected_target_fqdn})...")
    current_target = None
    for i in range(DNS_CHECK_RETRIES):
        current_target = get_cname_target(fqdn_to_check)
        if current_target == expected_target_fqdn:
            return current_target
        if (
            current_target == "TIMEOUT"
            or "ERROR_RESOLVING" in str(current_target)
            or ("FAILED_ALL_RETRIES_FOR" in str(current_target))
        ):
            break
        time.sleep(DNS_CHECK_DELAY)

    assert (
        current_target == expected_target_fqdn
    ), f"Expected DNS resolution for {fqdn_to_check} to be {expected_target_fqdn}, but got {current_target} after {DNS_CHECK_RETRIES} retries."
    return current_target


def test_dns_failover_cycle(route53_client, health_check_id):
    time.sleep(INITIAL_DNS_WAIT_PERIOD)

    perform_dns_check_with_retry(
        FAILOVER_RECORD_NAME,
        PRIMARY_API_GATEWAY_FQDN,
        "1. Verifying initial DNS resolution",
    )

    print(
        f"\n2. Inducing chaos for 'apigateway' and 'lambda' in region '{PRIMARY_API_REGION}'..."
    )
    fault_payload = [
        {"service": "apigateway", "region": PRIMARY_API_REGION},
        {"service": "lambda", "region": PRIMARY_API_REGION},
    ]
    try:
        response = requests.post(CHAOS_ENDPOINT, json=fault_payload, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Failed to inject chaos: {e}")
    time.sleep(FAILOVER_REACTION_WAIT)

    perform_dns_check_with_retry(
        FAILOVER_RECORD_NAME,
        SECONDARY_API_GATEWAY_FQDN,
        "3. Verifying DNS failover to secondary",
    )

    print(
        f"\n4. Clearing chaos for 'apigateway' and 'lambda' in region '{PRIMARY_API_REGION}'..."
    )
    try:
        response = requests.delete(CHAOS_ENDPOINT, json=fault_payload, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Failed to clear chaos: {e}")
    time.sleep(FAILOVER_REACTION_WAIT)

    perform_dns_check_with_retry(
        FAILOVER_RECORD_NAME,
        PRIMARY_API_GATEWAY_FQDN,
        "5. Verifying DNS failback to primary",
    )
