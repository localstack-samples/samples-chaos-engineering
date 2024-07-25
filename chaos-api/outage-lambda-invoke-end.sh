#!/bin/bash -xeu

curl --location --request DELETE 'http://localhost.localstack.cloud:4566/_localstack/chaos/faults' \
--header 'Content-Type: application/json' \
--data '
[
    {
        "service": "lambda",
        "operation": "Invoke",
        "probability": 1.0,
        "error": {
            "statusCode": 500,
            "code": "InternalServerError"
        }
    }
]'
