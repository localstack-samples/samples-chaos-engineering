echo "--- Step 1: Define Hosted Zone ---"
HOSTED_ZONE_NAME="hello-localstack.com"
RAW_HOSTED_ZONE_ID=$(awslocal route53 create-hosted-zone \
    --name "$HOSTED_ZONE_NAME" \
    --caller-reference "zone-$(date +%s)" | jq -r .HostedZone.Id)
CLEANED_HOSTED_ZONE_ID="${RAW_HOSTED_ZONE_ID#/hostedzone/}"
echo "Hosted Zone Name: $HOSTED_ZONE_NAME"
echo "Raw Hosted Zone ID: $RAW_HOSTED_ZONE_ID"
echo

export HOSTED_ZONE_NAME
export RAW_HOSTED_ZONE_ID

echo "--- Step 2: Define API Gateway and Health Check Parameters ---"
PRIMARY_API_ID="12345"
SECONDARY_API_ID="67890"
PRIMARY_API_REGION="us-east-1" # Define the region of your primary API Gateway

HEALTH_CHECK_RESOURCE_PATH="/dev/healthcheck"
PRIMARY_API_GATEWAY_FQDN="${PRIMARY_API_ID}.execute-api.localhost.localstack.cloud"
HEALTH_CHECK_PORT=4566

echo "Primary API ID: $PRIMARY_API_ID in region $PRIMARY_API_REGION"
echo "Primary API FQDN for Health Check: $PRIMARY_API_GATEWAY_FQDN"
echo "Health Check Port: $HEALTH_CHECK_PORT"
echo "Health Check Path: $HEALTH_CHECK_RESOURCE_PATH"
echo

echo "--- Step 3: Create Health Check for the Primary API Gateway ---"
# Health check can be created in any region, let's use us-west-1 as an example for the HC resource
HEALTH_CHECK_RESOURCE_REGION="us-west-1"
HEALTH_CHECK_ID=$(awslocal route53 create-health-check \
    --caller-reference "hc-app-${PRIMARY_API_ID}-$(date +%s)" \
    --region "$HEALTH_CHECK_RESOURCE_REGION" \
    --health-check-config "{
        \"FullyQualifiedDomainName\": \"${PRIMARY_API_GATEWAY_FQDN}\",
        \"Port\": ${HEALTH_CHECK_PORT},
        \"ResourcePath\": \"${HEALTH_CHECK_RESOURCE_PATH}\",
        \"Type\": \"HTTP\",
        \"RequestInterval\": 10,
        \"FailureThreshold\": 2
    }" | jq -r .HealthCheck.Id)
echo "Health Check ID created ($HEALTH_CHECK_ID) in region $HEALTH_CHECK_RESOURCE_REGION"
export HEALTH_CHECK_ID
echo
sleep 5

echo "--- Step 4: Verify Initial Health of Primary API Gateway (No Chaos) ---"
echo "Attempting to curl the primary health check endpoint directly (should be 200 OK):"
curl --connect-timeout 5 -v "http://${PRIMARY_API_GATEWAY_FQDN}:${HEALTH_CHECK_PORT}${HEALTH_CHECK_RESOURCE_PATH}"
echo
echo
echo "Fetching initial health check status from Route 53 (may take a few checks to show Success):"
sleep 25 # (RequestInterval * FailureThreshold + buffer)
# Query the health check status from the region it was created in
awslocal route53 get-health-check-status --health-check-id "$HEALTH_CHECK_ID" --region "$HEALTH_CHECK_RESOURCE_REGION"
echo
echo

echo "--- Step 5: Create CNAME Records for Regional API Endpoints ---"
PRIMARY_REGIONAL_DNS_NAME="${PRIMARY_API_ID}.${HOSTED_ZONE_NAME}"
SECONDARY_REGIONAL_DNS_NAME="${SECONDARY_API_ID}.${HOSTED_ZONE_NAME}"
PRIMARY_API_TARGET_FQDN="${PRIMARY_API_ID}.execute-api.localhost.localstack.cloud"
SECONDARY_API_TARGET_FQDN="${SECONDARY_API_ID}.execute-api.localhost.localstack.cloud"

CHANGE_BATCH_REGIONAL_CNAMES_JSON=$(printf '{
    "Comment": "Creating CNAMEs for regional API endpoints",
    "Changes": [
        {"Action": "UPSERT", "ResourceRecordSet": {"Name": "%s", "Type": "CNAME", "TTL": 60, "ResourceRecords": [{"Value": "%s"}]}},
        {"Action": "UPSERT", "ResourceRecordSet": {"Name": "%s", "Type": "CNAME", "TTL": 60, "ResourceRecords": [{"Value": "%s"}]}}
    ]
}' "$PRIMARY_REGIONAL_DNS_NAME" "$PRIMARY_API_TARGET_FQDN" "$SECONDARY_REGIONAL_DNS_NAME" "$SECONDARY_API_TARGET_FQDN")

echo "Creating/Updating CNAMEs for regional API Gateways..."
awslocal route53 change-resource-record-sets --hosted-zone-id "$RAW_HOSTED_ZONE_ID" --change-batch "$CHANGE_BATCH_REGIONAL_CNAMES_JSON"
echo

echo "--- Step 6: Create Failover Alias Records ---"
FAILOVER_RECORD_NAME="test.${HOSTED_ZONE_NAME}"
PRIMARY_FAILOVER_SET_ID="primary-app-${PRIMARY_API_ID}"
SECONDARY_FAILOVER_SET_ID="secondary-app-${SECONDARY_API_ID}"

CHANGE_BATCH_FAILOVER_ALIASES_JSON=$(printf '{
    "Comment": "Creating failover alias records for %s",
    "Changes": [
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "%s", "Type": "CNAME", "SetIdentifier": "%s", "Failover": "PRIMARY", "HealthCheckId": "%s",
                "AliasTarget": {"HostedZoneId": "%s", "DNSName": "%s", "EvaluateTargetHealth": true}
            }
        },
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "%s", "Type": "CNAME", "SetIdentifier": "%s", "Failover": "SECONDARY",
                "AliasTarget": {"HostedZoneId": "%s", "DNSName": "%s", "EvaluateTargetHealth": false}
            }
        }
    ]
}' "$FAILOVER_RECORD_NAME" \
   "$FAILOVER_RECORD_NAME" "$PRIMARY_FAILOVER_SET_ID" "$HEALTH_CHECK_ID" "$RAW_HOSTED_ZONE_ID" "$PRIMARY_REGIONAL_DNS_NAME" \
   "$FAILOVER_RECORD_NAME" "$SECONDARY_FAILOVER_SET_ID" "$RAW_HOSTED_ZONE_ID" "$SECONDARY_REGIONAL_DNS_NAME")

echo "Creating/Updating failover alias records for $FAILOVER_RECORD_NAME..."
awslocal route53 change-resource-record-sets --hosted-zone-id "$RAW_HOSTED_ZONE_ID" --change-batch "$CHANGE_BATCH_FAILOVER_ALIASES_JSON"
echo
