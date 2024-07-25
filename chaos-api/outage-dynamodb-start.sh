#!/bin/bash -xeu

curl --location --request PATCH 'http://localhost.localstack.cloud:4566/_localstack/chaos/faults' \
--header 'Content-Type: application/json' \
--data '
[
    {
        "service": "dynamodb",
        "probability": 1.0,
        "error": {
            "statusCode": 500,
            "code": "DatacentreNotFound"
        }
    }
]'
