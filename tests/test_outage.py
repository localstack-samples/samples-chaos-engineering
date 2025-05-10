import pytest
import time
import boto3
import requests
import os
import json
import botocore

LOCALSTACK_ENDPOINT_URL = os.environ.get(
    "LOCALSTACK_ENDPOINT_URL", "http://localhost:4566"
)
CHAOS_ENDPOINT = f"{LOCALSTACK_ENDPOINT_URL}/_localstack/chaos/faults"

DYNAMODB_TABLE_NAME = "Products"
SERVICE_REGION = "us-east-1"
PRIMARY_API_ID = "12345"
API_GATEWAY_PORT = 4566
ADD_PRODUCT_URL = f"http://{PRIMARY_API_ID}.execute-api.localhost.localstack.cloud:{API_GATEWAY_PORT}/dev/productApi"

BASE_PRODUCT_DATA = {
    "name": "Pytest Widget",
    "price": "25.99",
    "description": "A widget specifically for Pytest scenarios.",
}

DYNAMODB_OUTAGE_REACTION_WAIT = 10
SERVICE_RECOVERY_WAIT = 30


def manage_chaos(service_name, region_name, induce=True, timeout=10):
    fault_payload = [{"service": service_name, "region": region_name}]
    action_str = "Inducing" if induce else "Clearing"
    try:
        if induce:
            response = requests.post(
                CHAOS_ENDPOINT, json=fault_payload, timeout=timeout
            )
        else:
            response = requests.delete(
                CHAOS_ENDPOINT, json=fault_payload, timeout=timeout
            )
        response.raise_for_status()
        if induce:
            return response.json()
        else:
            return []
    except requests.exceptions.RequestException as e:
        pytest.fail(
            f"Failed to {action_str.lower()} chaos for {service_name} in {region_name}: {e}"
        )
    except json.JSONDecodeError as e:
        current_response_text = (
            response.text
            if "response" in locals()
            else "Response object not available or no text."
        )
        pytest.fail(
            f"Failed to parse JSON response when {action_str.lower()} chaos: {e}. Response text: {current_response_text}"
        )
    return None


def check_active_faults(expected_to_be_present_or_absent, present=True, timeout=5):
    try:
        response = requests.get(CHAOS_ENDPOINT, timeout=timeout)
        response.raise_for_status()
        active_faults = response.json()

        normalize_fault = lambda d: tuple(sorted(d.items()))
        normalized_active_set = {normalize_fault(f) for f in active_faults}

        if not expected_to_be_present_or_absent and not present:
            assert (
                not active_faults
            ), f"Expected no active faults, but got: {active_faults}"
            return

        normalized_expected_set = {
            normalize_fault(f) for f in expected_to_be_present_or_absent
        }

        if present:
            assert normalized_expected_set.issubset(
                normalized_active_set
            ), f"Expected faults {expected_to_be_present_or_absent} to be active, but active set is {active_faults}"
        else:
            assert not normalized_expected_set.intersection(
                normalized_active_set
            ), f"Expected faults {expected_to_be_present_or_absent} to be cleared, but some were found in active set: {active_faults}"

    except requests.exceptions.RequestException as e:
        pytest.fail(f"Failed to GET active faults: {e}")
    except json.JSONDecodeError as e:
        current_response_text = (
            response.text
            if "response" in locals()
            else "Response object not available or no text."
        )
        pytest.fail(
            f"Failed to parse JSON response from GET /faults: {e}. Response text: {current_response_text}"
        )


@pytest.fixture(scope="session")
def dynamodb_resource():
    return boto3.resource(
        "dynamodb", endpoint_url=LOCALSTACK_ENDPOINT_URL, region_name=SERVICE_REGION
    )


@pytest.fixture(scope="session")
def lambda_client():
    return boto3.client(
        "lambda", endpoint_url=LOCALSTACK_ENDPOINT_URL, region_name=SERVICE_REGION
    )


def test_dynamodb_table_exists(dynamodb_resource):
    try:
        table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)
        table.load()
    except Exception as e:
        pytest.fail(
            f"DynamoDB table '{DYNAMODB_TABLE_NAME}' not found or not accessible in region {SERVICE_REGION}: {e}"
        )


def test_add_product_lambda_exists(lambda_client):
    try:
        lambda_client.get_function(FunctionName="add-product")
    except Exception as e:
        pytest.fail(
            f"Lambda function 'add-product' not found in region {SERVICE_REGION}: {e}"
        )


def test_dynamodb_outage_impacts_add_product(dynamodb_resource):
    headers = {"Content-Type": "application/json"}
    expected_plain_text_success_message = "Product added/updated successfully."
    expected_outage_message = "A DynamoDB error occurred. Message sent to queue."

    ts = int(time.time())
    normal_product_id = f"prod-normal-{ts}"
    normal_data = {
        "id": normal_product_id,
        "name": f"Normal Widget {ts}",
        "price": BASE_PRODUCT_DATA["price"],
        "description": f"{BASE_PRODUCT_DATA['description']} (Normal Operation)",
    }

    outage_attempt_product_id = f"prod-outage-{ts}"
    outage_data = {
        "id": outage_attempt_product_id,
        "name": f"Outage Attempt Widget {ts}",
        "price": "0.00",
        "description": f"{BASE_PRODUCT_DATA['description']} (During Outage Attempt)",
    }

    restored_product_id = f"prod-restored-{ts + 1}"
    restored_data = {
        "id": restored_product_id,
        "name": f"Restored Widget {ts+1}",
        "price": "26.99",
        "description": f"{BASE_PRODUCT_DATA['description']} (Post Recovery)",
    }

    response_normal = None
    try:
        response_normal = requests.post(
            ADD_PRODUCT_URL, headers=headers, json=normal_data, timeout=10
        )
        response_normal.raise_for_status()
        assert expected_plain_text_success_message in response_normal.text
        table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)
        item = table.get_item(Key={"id": normal_product_id}).get("Item")
        assert item is not None and item["name"] == normal_data["name"]
    except requests.exceptions.HTTPError as http_err:
        pytest.fail(
            f"HTTP error during normal operation: {http_err} - Response: {http_err.response.text if http_err.response else 'N/A'}"
        )
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Network/Request error during normal operation: {e}")
    except Exception as e:
        response_text = (
            response_normal.text if response_normal else "Response object not available"
        )
        pytest.fail(
            f"Error during normal operation verification: {e} (Response text was: '{response_text}')"
        )

    faults_to_induce = [{"service": "dynamodb", "region": SERVICE_REGION}]
    manage_chaos(service_name="dynamodb", region_name=SERVICE_REGION, induce=True)
    check_active_faults(expected_to_be_present_or_absent=faults_to_induce, present=True)
    time.sleep(DYNAMODB_OUTAGE_REACTION_WAIT)

    response_outage = None
    try:
        response_outage = requests.post(
            ADD_PRODUCT_URL, headers=headers, json=outage_data, timeout=10
        )
        assert (
            response_outage.status_code == 200
        ), f"Expected status code 200 during graceful handling, got {response_outage.status_code}."
        assert (
            expected_outage_message in response_outage.text
        ), f"Expected outage message '{expected_outage_message}' not found. Got: '{response_outage.text}'"

        table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)
        try:
            item_response_during_outage = table.get_item(
                Key={"id": outage_attempt_product_id}
            )
            item_during_outage = item_response_during_outage.get("Item")
            if item_during_outage is not None:
                pytest.fail(
                    f"Product '{outage_attempt_product_id}' WAS FOUND in DynamoDB during outage, which is unexpected."
                )
        except botocore.exceptions.ClientError as ce:
            error_code = ce.response.get("Error", {}).get("Code")
            assert (
                "ServiceUnavailable" in str(ce)
                or "ProvisionedThroughputExceededException" in str(ce)
                or error_code == "ServiceUnavailable"
            ), f"Expected ServiceUnavailable from DynamoDB due to chaos, but got: {ce}"

    except requests.exceptions.RequestException as e:
        pytest.fail(
            f"Request to API Gateway failed during outage test, unexpected if Lambda handles gracefully: {e}"
        )
    except Exception as e:
        response_text = (
            response_outage.text if response_outage else "Response object not available"
        )
        pytest.fail(
            f"Unexpected generic error during outage product addition test step: {e} (API Response text: '{response_text}')"
        )

    manage_chaos(service_name="dynamodb", region_name=SERVICE_REGION, induce=False)
    check_active_faults(
        expected_to_be_present_or_absent=faults_to_induce, present=False
    )
    time.sleep(SERVICE_RECOVERY_WAIT)

    response_restored = None
    try:
        response_restored = requests.post(
            ADD_PRODUCT_URL, headers=headers, json=restored_data, timeout=10
        )
        response_restored.raise_for_status()
        assert expected_plain_text_success_message in response_restored.text
        table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)
        item_restored = table.get_item(Key={"id": restored_product_id}).get("Item")
        assert (
            item_restored is not None and item_restored["name"] == restored_data["name"]
        )
    except requests.exceptions.HTTPError as http_err:
        pytest.fail(
            f"HTTP error during post-recovery: {http_err} - Response: {http_err.response.text if http_err.response else 'N/A'}"
        )
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Network/Request error during post-recovery: {e}")
    except Exception as e:
        response_text = (
            response_restored.text
            if response_restored
            else "Response object not available"
        )
        pytest.fail(
            f"Error during post-recovery: {e} (Response text: '{response_text}')"
        )
