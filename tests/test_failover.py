import pytest
import time
import requests
import dns.resolver
import os
import boto3

LOCALSTACK_ENDPOINT_URL = os.environ.get("LOCALSTACK_ENDPOINT_URL", "http://localhost:4566")
CHAOS_ENDPOINT = f"{LOCALSTACK_ENDPOINT_URL}/_localstack/chaos/faults"

HOSTED_ZONE_NAME = "hello-localstack.com"
PRIMARY_API_ID = "12345"
SECONDARY_API_ID = "67890"
PRIMARY_API_REGION = "us-east-1"
HEALTH_CHECK_RESOURCE_REGION = "us-west-1"
HEALTH_CHECK_PORT = 4566
HEALTH_CHECK_RESOURCE_PATH = "/dev/healthcheck"

PRIMARY_API_GATEWAY_FQDN = f"{PRIMARY_API_ID}.execute-api.localhost.localstack.cloud"
SECONDARY_API_GATEWAY_FQDN = f"{SECONDARY_API_ID}.execute-api.localhost.localstack.cloud"
FAILOVER_RECORD_NAME = f"test.{HOSTED_ZONE_NAME}"

HEALTH_CHECK_INTERVAL = 10
HEALTH_CHECK_FAILURE_THRESHOLD = 2
INITIAL_DNS_WAIT_PERIOD = 10
DNS_CHECK_RETRIES = 4
DNS_CHECK_DELAY = 5
FAILOVER_REACTION_WAIT = (HEALTH_CHECK_INTERVAL * HEALTH_CHECK_FAILURE_THRESHOLD) + 25

def get_cname_target(hostname, dns_server='127.0.0.1', port=53, max_cname_hops=5):
    """
    Resolves a hostname and follows the CNAME chain.
    It aims to return the FQDN that matches the *.execute-api.localhost.localstack.cloud pattern,
    or the last CNAME target if that pattern is not explicitly hit within max_cname_hops but was seen.
    """
    resolver = dns.resolver.Resolver()
    resolver.nameservers = [dns_server]
    resolver.port = port
    resolver.timeout = 2
    resolver.lifetime = 5

    current_hostname = hostname
    last_seen_api_gateway_pattern_fqdn = None

    print(f"   Resolving ultimate CNAME target for: {current_hostname} using DNS server {dns_server}:{port}")
    
    for hop in range(max_cname_hops):
        if ".execute-api.localhost.localstack.cloud" in current_hostname:
            print(f"   CNAME trace: Current hostname '{current_hostname}' matches API gateway pattern. Considering it final.")
            return current_hostname
        
        last_seen_api_gateway_pattern_fqdn = current_hostname

        print(f"   CNAME trace (Hop {hop+1}/{max_cname_hops}): Querying '{current_hostname}' for CNAME...")
        try:
            answers = resolver.resolve(current_hostname, 'CNAME') 
            if answers and len(answers) > 0:
                new_target = str(answers[0].target).rstrip('.')
                print(f"   CNAME trace: '{current_hostname}' -> CNAME -> '{new_target}'")
                
                if not new_target or new_target == current_hostname: 
                    print(f"   CNAME trace: Detected CNAME loop or empty target at '{current_hostname}'. Returning previous or current.")
                    return current_hostname
                
                current_hostname = new_target
                if ".execute-api.localhost.localstack.cloud" in current_hostname:
                    print(f"   CNAME trace: New target '{current_hostname}' matches API gateway pattern.")
                    return current_hostname
            else: 
                print(f"   CNAME trace: Query for '{current_hostname}' successful but no CNAME records. Assuming it's the final target.")
                return current_hostname

        except dns.resolver.NoAnswer:
            print(f"   CNAME trace: No CNAME answer specifically for '{current_hostname}'. This is considered the final target in the chain.")
            return current_hostname 
        except dns.resolver.NXDOMAIN:
            print(f"   CNAME trace: NXDOMAIN for '{current_hostname}'. Record does not exist.")
            return "NXDOMAIN"
        except dns.exception.Timeout:
            print(f"   CNAME trace: Timeout querying '{current_hostname}'.")
            return "TIMEOUT"
        except Exception as e:
            print(f"   CNAME trace: Error querying '{current_hostname}': {type(e).__name__} - {e}")
            return f"ERROR_RESOLVING"

    print(f"   CNAME trace: Exceeded max CNAME hops ({max_cname_hops}) for original '{hostname}'. Last known target: '{current_hostname}'")
    return current_hostname


@pytest.fixture(scope="session")
def route53_client():
    return boto3.client("route53", endpoint_url=LOCALSTACK_ENDPOINT_URL, region_name=HEALTH_CHECK_RESOURCE_REGION)

@pytest.fixture(scope="session")
def health_check_id(route53_client):
    print("\n--- Fixture: Locating existing Health Check ID ---")
    try:
        paginator = route53_client.get_paginator('list_health_checks')
        for page in paginator.paginate():
            for hc in page.get('HealthChecks', []):
                config = hc.get('HealthCheckConfig', {})
                if config.get('FullyQualifiedDomainName') == PRIMARY_API_GATEWAY_FQDN and \
                   config.get('Port') == HEALTH_CHECK_PORT and \
                   config.get('ResourcePath') == HEALTH_CHECK_RESOURCE_PATH:
                    found_id = hc['Id']
                    print(f"Found existing Health Check ID: {found_id} for {PRIMARY_API_GATEWAY_FQDN}")
                    return found_id
        pytest.fail(f"Could not find an existing health check for {PRIMARY_API_GATEWAY_FQDN}:{HEALTH_CHECK_PORT}{HEALTH_CHECK_RESOURCE_PATH}")
    except Exception as e:
        pytest.fail(f"Error trying to find health check ID: {e}")
    return None


def perform_dns_check_with_retry(fqdn_to_check, expected_target_fqdn, step_name):
    """Helper to perform DNS check with retries and assert."""
    print(f"\n{step_name} (expecting: {expected_target_fqdn})...")
    current_target = None
    for i in range(DNS_CHECK_RETRIES):
        print(f"   Attempt {i+1}/{DNS_CHECK_RETRIES} to resolve {fqdn_to_check}...")
        current_target = get_cname_target(fqdn_to_check)
        print(f"   DNS ultimate target for {fqdn_to_check}: {current_target}")
        if current_target == expected_target_fqdn:
            print(f"   Successfully resolved {fqdn_to_check} to {expected_target_fqdn}.")
            return current_target 
        if current_target == "TIMEOUT" or "ERROR_RESOLVING" in str(current_target) or ("FAILED_ALL_RETRIES_FOR" in str(current_target)):
            print(f"   Definitive error resolving, will not pass. current_target: {current_target}")
            break 
        print(f"   Retrying in {DNS_CHECK_DELAY}s...")
        time.sleep(DNS_CHECK_DELAY)
    
    assert current_target == expected_target_fqdn, \
        f"Expected DNS resolution for {fqdn_to_check} to be {expected_target_fqdn}, but got {current_target} after {DNS_CHECK_RETRIES} retries."
    return current_target


def test_dns_failover_cycle(route53_client, health_check_id):
    print(f"\n--- Test Case: DNS Failover and Failback ---")
    print(f"Using Health Check ID: {health_check_id}")
    print(f"Testing FQDN: {FAILOVER_RECORD_NAME}")
    print(f"Primary expected ultimate target: {PRIMARY_API_GATEWAY_FQDN}")
    print(f"Secondary expected ultimate target: {SECONDARY_API_GATEWAY_FQDN}")

    print(f"\n0. Performing initial wait ({INITIAL_DNS_WAIT_PERIOD}s) for DNS records to propagate...")
    time.sleep(INITIAL_DNS_WAIT_PERIOD)

    perform_dns_check_with_retry(FAILOVER_RECORD_NAME, PRIMARY_API_GATEWAY_FQDN, "1. Verifying initial DNS resolution")

    print(f"\n2. Inducing chaos for 'apigateway' and 'lambda' in region '{PRIMARY_API_REGION}'...")
    fault_payload = [
        {"service": "apigateway", "region": PRIMARY_API_REGION},
        {"service": "lambda", "region": PRIMARY_API_REGION}
    ]
    try:
        response = requests.post(CHAOS_ENDPOINT, json=fault_payload, timeout=10)
        response.raise_for_status()
        print(f"   Chaos injection successful: {response.json()}")
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Failed to inject chaos: {e}")

    print(f"   Waiting {FAILOVER_REACTION_WAIT}s for failover to occur...")
    time.sleep(FAILOVER_REACTION_WAIT)

    perform_dns_check_with_retry(FAILOVER_RECORD_NAME, SECONDARY_API_GATEWAY_FQDN, "3. Verifying DNS failover to secondary")

    print(f"\n4. Clearing chaos for 'apigateway' and 'lambda' in region '{PRIMARY_API_REGION}'...")
    try:
        response = requests.delete(CHAOS_ENDPOINT, json=fault_payload, timeout=10)
        response.raise_for_status()
        print(f"   Chaos clear response status: {response.status_code}, content: {response.text[:100]}...")
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Failed to clear chaos: {e}")

    print(f"   Waiting {FAILOVER_REACTION_WAIT}s for failback to occur...")
    time.sleep(FAILOVER_REACTION_WAIT)

    perform_dns_check_with_retry(FAILOVER_RECORD_NAME, PRIMARY_API_GATEWAY_FQDN, "5. Verifying DNS failback to primary")

    print("\n--- DNS Failover and Failback Test Completed Successfully ---")
