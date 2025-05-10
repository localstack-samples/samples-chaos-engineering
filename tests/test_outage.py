import pytest
import time
import boto3
import requests
import os
import json 
import botocore 

# --- Configuration Constants ---
LOCALSTACK_ENDPOINT_URL = os.environ.get("LOCALSTACK_ENDPOINT_URL", "http://localhost:4566")
CHAOS_ENDPOINT = f"{LOCALSTACK_ENDPOINT_URL}/_localstack/chaos/faults"

DYNAMODB_TABLE_NAME = "Products"
SERVICE_REGION = "us-east-1" 

PRIMARY_API_ID = "12345" 
API_GATEWAY_PORT = 4566 
ADD_PRODUCT_URL = f"http://{PRIMARY_API_ID}.execute-api.localhost.localstack.cloud:{API_GATEWAY_PORT}/dev/productApi"

# Base product data (static parts) - we'll create full data with unique IDs in the test
BASE_PRODUCT_DATA = {
    "name": "Pytest Widget",
    "price": "25.99", # Slightly different price for easier differentiation if needed
    "description": "A widget specifically for Pytest scenarios.",
}

# Timings
DYNAMODB_OUTAGE_REACTION_WAIT = 10 
SERVICE_RECOVERY_WAIT = 30 

# --- Helper Functions for Chaos (remain the same as your working version) ---

def manage_chaos(service_name, region_name, induce=True, timeout=10):
    """Induces or clears chaos for a specific service and region."""
    fault_payload = [{"service": service_name, "region": region_name}]
    action_str = "Inducing" if induce else "Clearing"
    
    print(f"\n--- {action_str} chaos for service '{service_name}' in region '{region_name}' ---")

    try:
        if induce:
            response = requests.post(CHAOS_ENDPOINT, json=fault_payload, timeout=timeout)
        else:
            response = requests.delete(CHAOS_ENDPOINT, json=fault_payload, timeout=timeout)
        
        response.raise_for_status() 
        
        if induce:
            active_faults_after_induce = response.json()
            print(f"   Chaos injection successful. Active faults reported: {active_faults_after_induce}")
            return active_faults_after_induce 
        else:
            print(f"   Chaos clear request successful. Status: {response.status_code}, Response: {response.text[:100]}")
            return [] 
            
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Failed to {action_str.lower()} chaos for {service_name} in {region_name}: {e}")
    except json.JSONDecodeError as e: 
        current_response_text = response.text if 'response' in locals() else "Response object not available or no text."
        pytest.fail(f"Failed to parse JSON response when {action_str.lower()} chaos: {e}. Response text: {current_response_text}")
    return None

def check_active_faults(expected_to_be_present_or_absent, present=True, timeout=5):
    action_str = "present" if present else "absent"
    print(f"--- Checking chaos faults (expecting specific faults to be {action_str}: {expected_to_be_present_or_absent}) ---")
    try:
        response = requests.get(CHAOS_ENDPOINT, timeout=timeout)
        response.raise_for_status()
        active_faults = response.json()
        print(f"   Active faults reported by Chaos API: {active_faults}")

        normalize_fault = lambda d: tuple(sorted(d.items()))
        normalized_active_set = {normalize_fault(f) for f in active_faults}

        if not expected_to_be_present_or_absent and not present: 
            assert not active_faults, f"Expected no active faults, but got: {active_faults}"
            print("   Verified no active faults are present.")
            return

        normalized_expected_set = {normalize_fault(f) for f in expected_to_be_present_or_absent}

        if present:
            assert normalized_expected_set.issubset(normalized_active_set), \
                f"Expected faults {expected_to_be_present_or_absent} to be active, but active set is {active_faults}"
            print(f"   Verified expected faults are active.")
        else: 
            assert not normalized_expected_set.intersection(normalized_active_set), \
                f"Expected faults {expected_to_be_present_or_absent} to be cleared, but some were found in active set: {active_faults}"
            print(f"   Verified expected faults are cleared (not present).")

    except requests.exceptions.RequestException as e:
        pytest.fail(f"Failed to GET active faults: {e}")
    except json.JSONDecodeError as e:
        current_response_text = response.text if 'response' in locals() else "Response object not available or no text."
        pytest.fail(f"Failed to parse JSON response from GET /faults: {e}. Response text: {current_response_text}")

# --- Pytest Fixtures (remain the same) ---

@pytest.fixture(scope="session")
def dynamodb_resource():
    return boto3.resource("dynamodb", endpoint_url=LOCALSTACK_ENDPOINT_URL, region_name=SERVICE_REGION)

@pytest.fixture(scope="session")
def lambda_client():
    return boto3.client("lambda", endpoint_url=LOCALSTACK_ENDPOINT_URL, region_name=SERVICE_REGION)

# --- Prerequisite Tests (remain the same) ---

def test_dynamodb_table_exists(dynamodb_resource):
    print("\n--- Prerequisite: Checking DynamoDB table existence ---")
    try:
        table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)
        table.load() 
        print(f"   DynamoDB table '{DYNAMODB_TABLE_NAME}' found in region {dynamodb_resource.meta.client.meta.region_name}.")
    except Exception as e: 
        pytest.fail(f"DynamoDB table '{DYNAMODB_TABLE_NAME}' not found or not accessible in region {SERVICE_REGION}: {e}")

def test_add_product_lambda_exists(lambda_client):
    print("\n--- Prerequisite: Checking 'add-product' Lambda function existence ---")
    try:
        lambda_client.get_function(FunctionName="add-product")
        print(f"   Lambda function 'add-product' found in region {lambda_client.meta.region_name}.")
    except Exception as e: 
        pytest.fail(f"Lambda function 'add-product' not found in region {SERVICE_REGION}: {e}")

# --- Main Test Function for DynamoDB Outage ---

def test_dynamodb_outage_impacts_add_product(dynamodb_resource):
    headers = {"Content-Type": "application/json"}
    expected_plain_text_success_message = "Product added/updated successfully."
    expected_outage_message = "A DynamoDB error occurred. Message sent to queue."

    # --- MODIFICATION: Define unique data for each stage ---
    ts = int(time.time())
    normal_product_id = f"prod-normal-{ts}"
    normal_data = {
        "id": normal_product_id,
        "name": f"Normal Widget {ts}",
        "price": BASE_PRODUCT_DATA["price"],
        "description": f"{BASE_PRODUCT_DATA['description']} (Normal Operation)"
    }

    outage_attempt_product_id = f"prod-outage-{ts}"
    outage_data = {
        "id": outage_attempt_product_id,
        "name": f"Outage Attempt Widget {ts}",
        "price": "0.00", # e.g., different price for outage attempt
        "description": f"{BASE_PRODUCT_DATA['description']} (During Outage Attempt)"
    }

    restored_product_id = f"prod-restored-{ts + 1}" # Ensure slightly different timestamp if needed
    restored_data = {
        "id": restored_product_id,
        "name": f"Restored Widget {ts+1}",
        "price": "26.99", # Different price again
        "description": f"{BASE_PRODUCT_DATA['description']} (Post Recovery)"
    }
    # --- END MODIFICATION ---


    # 1. Verify product can be added when DynamoDB is healthy
    print("\n--- Test Step 1: Verify normal operation (add product) ---")
    response_normal = None
    try:
        print(f"   Attempting to add product: {normal_data} to {ADD_PRODUCT_URL}")
        response_normal = requests.post(ADD_PRODUCT_URL, headers=headers, json=normal_data, timeout=10)
        print(f"   Response status (normal): {response_normal.status_code}, Text: '{response_normal.text}'")
        response_normal.raise_for_status() 
        assert expected_plain_text_success_message in response_normal.text
        print(f"   Successfully added product before outage.")
        table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)
        item = table.get_item(Key={'id': normal_product_id}).get('Item')
        assert item is not None and item['name'] == normal_data['name']
        print(f"   Verified product '{normal_product_id}' in DynamoDB.")
    except requests.exceptions.HTTPError as http_err:
        pytest.fail(f"HTTP error during normal operation: {http_err} - Response: {http_err.response.text if http_err.response else 'N/A'}")
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Network/Request error during normal operation: {e}")
    except Exception as e:
        response_text = response_normal.text if response_normal else "Response object not available"
        pytest.fail(f"Error during normal operation verification: {e} (Response text was: '{response_text}')")

    # 2. Induce DynamoDB outage in SERVICE_REGION
    faults_to_induce = [{"service": "dynamodb", "region": SERVICE_REGION}]
    manage_chaos(service_name="dynamodb", region_name=SERVICE_REGION, induce=True)
    check_active_faults(expected_to_be_present_or_absent=faults_to_induce, present=True) 
    print(f"   Waiting {DYNAMODB_OUTAGE_REACTION_WAIT}s for outage to take effect...")
    time.sleep(DYNAMODB_OUTAGE_REACTION_WAIT)

    # 3. Verify adding a product is gracefully handled (returns 200 with specific message)
    print("\n--- Test Step 3: Verify add product is gracefully handled during DynamoDB outage ---")
    response_outage = None
    try:
        print(f"   Attempting to add product during outage: {outage_data}")
        response_outage = requests.post(ADD_PRODUCT_URL, headers=headers, json=outage_data, timeout=10)
        print(f"   Response status (outage): {response_outage.status_code}, Text: '{response_outage.text}'")
        
        assert response_outage.status_code == 200, \
            f"Expected status code 200 during graceful handling, got {response_outage.status_code}."
        assert expected_outage_message in response_outage.text, \
            f"Expected outage message '{expected_outage_message}' not found. Got: '{response_outage.text}'"
        print(f"   Received expected graceful handling message during outage.")
        
        table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)
        print(f"   Attempting to verify product '{outage_attempt_product_id}' is NOT in DynamoDB (expecting GetItem to fail)...")
        try:
            item_response_during_outage = table.get_item(Key={'id': outage_attempt_product_id})
            item_during_outage = item_response_during_outage.get('Item')
            if item_during_outage is not None:
                pytest.fail(f"Product '{outage_attempt_product_id}' WAS FOUND in DynamoDB during outage, which is unexpected.")
            print(f"   GetItem for '{outage_attempt_product_id}' succeeded but returned no item (good, item not found).")
        except botocore.exceptions.ClientError as ce:
            error_code = ce.response.get('Error', {}).get('Code')
            assert "ServiceUnavailable" in str(ce) or "ProvisionedThroughputExceededException" in str(ce) or error_code == "ServiceUnavailable" , \
                f"Expected ServiceUnavailable from DynamoDB due to chaos, but got: {ce}"
            print(f"   Correctly received ClientError ({type(ce).__name__}: {error_code}) when trying to GetItem during outage: {ce}")
            print(f"   This confirms product '{outage_attempt_product_id}' could not be read (and thus likely not written) from DynamoDB during outage.")
        
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Request to API Gateway failed during outage test, unexpected if Lambda handles gracefully: {e}")
    except Exception as e: 
        response_text = response_outage.text if response_outage else "Response object not available"
        pytest.fail(f"Unexpected generic error during outage product addition test step: {e} (API Response text: '{response_text}')")

    # 4. Clear DynamoDB outage
    manage_chaos(service_name="dynamodb", region_name=SERVICE_REGION, induce=False)
    check_active_faults(expected_to_be_present_or_absent=faults_to_induce, present=False) 
    print(f"   Waiting {SERVICE_RECOVERY_WAIT}s for DynamoDB to recover...")
    time.sleep(SERVICE_RECOVERY_WAIT)

    # 5. Verify product can be added again after outage is cleared
    print("\n--- Test Step 5: Verify normal operation restored (add product) ---")
    response_restored = None
    try:
        print(f"   Attempting to add product after outage cleared: {restored_data}")
        response_restored = requests.post(ADD_PRODUCT_URL, headers=headers, json=restored_data, timeout=10)
        print(f"   Response status (restored): {response_restored.status_code}, Text: '{response_restored.text}'")
        response_restored.raise_for_status()
        assert expected_plain_text_success_message in response_restored.text
        print(f"   Successfully added product after outage cleared.")
        table = dynamodb_resource.Table(DYNAMODB_TABLE_NAME)
        item_restored = table.get_item(Key={'id': restored_product_id}).get('Item')
        assert item_restored is not None and item_restored['name'] == restored_data['name']
        print(f"   Verified product '{restored_product_id}' in DynamoDB after recovery.")
    except requests.exceptions.HTTPError as http_err:
        pytest.fail(f"HTTP error during post-recovery: {http_err} - Response: {http_err.response.text if http_err.response else 'N/A'}")
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Network/Request error during post-recovery: {e}")
    except Exception as e:
        response_text = response_restored.text if response_restored else "Response object not available"
        pytest.fail(f"Error during post-recovery: {e} (Response text: '{response_text}')")

    print("\n--- DynamoDB Outage Test Completed Successfully ---")
