#!/bin/bash -xeu

curl --location --request POST 'http://localhost.localstack.cloud:4566/_localstack/chaos/effects' \
--header 'Content-Type: application/json' \
--data '{
    "latency": 5000
}'
