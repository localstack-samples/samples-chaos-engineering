import boto3
import json

localstack_hostname = os.getenv('LOCALSTACK_HOSTNAME', 'localhost')

# Initialize the DynamoDB client
dynamodb = boto3.client('dynamodb', endpoint_url=f'http://{localstack_hostname}:4566',region_name=us-east-1)

# The target DynamoDB table where you want to replicate your data
TARGET_TABLE_NAME = 'Products'

def lambda_handler(event, context):
    # Loop through each record in the event
    for record in event['Records']:
        # Check if the event is an insert or modify
        if record['eventName'] == 'INSERT' or record['eventName'] == 'MODIFY':
            # Get the new image of the item
            new_image = record['dynamodb']['NewImage']

            # Convert the new image to the format expected by DynamoDB
            item = {k: format_attribute(v) for k, v in new_image.items()}

            # Put the item in the target table
            try:
                response = dynamodb.put_item(
                    TableName=TARGET_TABLE_NAME,
                    Item=item
                )
                print(f"PutItem succeeded: {json.dumps(response, indent=4)}")
            except Exception as e:
                print(f"Error putting item to TargetTable: {e}")
                continue  # Skip to the next record in case of error

    # Return successfully processed records
    return {
        'statusCode': 200,
        'body': json.dumps(f"Processed {len(event['Records'])} records.")
    }

def format_attribute(value):
    """Convert value from DynamoDB's format to the format put_item expects."""
    if 'S' in value:
        return {'S': value['S']}
    elif 'N' in value:
        return {'N': value['N']}
    elif 'BOOL' in value:
        return {'BOOL': value['BOOL']}
    elif 'M' in value:
        return {'M': {k: format_attribute(v) for k, v in value['M'].items()}}
    elif 'L' in value:
        return {'L': [format_attribute(v) for v in value['L']]}
    # Add other data types as needed
    else:
        raise ValueError("Unknown data type found in value: " + json.dumps(value))

