# Chaos Plugin

| Environment      | <img src="https://img.shields.io/badge/LocalStack-deploys-4D29B4.svg?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAKgAAACoABZrFArwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAALbSURBVHic7ZpNaxNRFIafczNTGIq0G2M7pXWRlRv3Lusf8AMFEQT3guDWhX9BcC/uFAr1B4igLgSF4EYDtsuQ3M5GYrTaj3Tmui2SpMnM3PlK3m1uzjnPw8xw50MoaNrttl+r1e4CNRv1jTG/+v3+c8dG8TSilHoAPLZVX0RYWlraUbYaJI2IuLZ7KKUWCisgq8wF5D1A3rF+EQyCYPHo6Ghh3BrP8wb1en3f9izDYlVAp9O5EkXRB8dxxl7QBoNBpLW+7fv+a5vzDIvVU0BELhpjJrmaK2NMw+YsIxunUaTZbLrdbveZ1vpmGvWyTOJToNlsuqurq1vAdWPMeSDzwzhJEh0Bp+FTmifzxBZQBXiIKaAq8BBDQJXgYUoBVYOHKQRUER4mFFBVeJhAQJXh4QwBVYeHMQJmAR5GCJgVeBgiYJbg4T8BswYPp+4GW63WwvLy8hZwLcd5TudvBj3+OFBIeA4PD596nvc1iiIrD21qtdr+ysrKR8cY42itCwUP0Gg0+sC27T5qb2/vMunB/0ipTmZxfN//orW+BCwmrGV6vd63BP9P2j9WxGbxbrd7B3g14fLfwFsROUlzBmNM33XdR6Meuxfp5eg54IYxJvXCx8fHL4F3w36blTdDI4/0WREwMnMBeQ+Qd+YC8h4g78wF5D1A3rEqwBiT6q4ubpRSI+ewuhP0PO/NwcHBExHJZZ8PICI/e73ep7z6zzNPwWP1djhuOp3OfRG5kLROFEXv19fXP49bU6TbYQDa7XZDRF6kUUtEtoFb49YUbh/gOM7YbwqnyG4URQ/PWlQ4ASllNwzDzY2NDX3WwioKmBgeqidgKnioloCp4aE6AmLBQzUExIaH8gtIBA/lFrCTFB7KK2AnDMOrSeGhnAJSg4fyCUgVHsolIHV4KI8AK/BQDgHW4KH4AqzCQwEfiIRheKKUAvjuuu7m2tpakPdMmcYYI1rre0EQ1LPo9w82qyNziMdZ3AAAAABJRU5ErkJggg=="> |
|------------------|-----------------------------------------|
| __Services__     | API Gateway, Lambda, DynamoDB, SNS, SQS |
| __Categories__   | LocalStack Pro, Init Hooks, Java SDK    |


## Description

In this sample, we use LocalStack Chaos Plugin to cause controlled outages in the DynamoDB service to study the resiliency of the architecture and improve fault tolerance.
This kind of test helps to ensure that the software can handle database downtime gracefully by implementing strategies such as queuing requests to prevent data loss.
This proactive error handling ensures that the system can maintain its operations despite partial failures.

![arch-1](images/arch-1.png)


## Prerequisites

- [Maven 3.8.5](https://maven.apache.org/install.html) & [Java 17](https://www.java.com/en/download/help/download_options.html)
- [LocalStack](https://localstack.cloud/)
- [Docker](https://docs.docker.com/get-docker/) - for running LocalStack


## Before starting

Make sure to build the Lambda function by running the following command in the root folder

```
cd lambda-functions && mvn clean package shade:shade
```


### Starting LocalStack

```bash
export LOCALSTACK_AUTH_TOKEN = <your_localstack_auth_token>
docker compose up
```

### Creating the resources

The resources are created via `init hooks` at startup, using the `init-resources.sh` file.

### Creating a Product

Using cURL we can create a Product entity:

```text
$ curl --location 'http://12345.execute-api.localhost.localstack.cloud:4566/dev/productApi' \
--header 'Content-Type: application/json' \
--data '{
  "id": "prod-2004",
  "name": "Ultimate Gadget",
  "price": "49.99",
  "description": "The Ultimate Gadget is the perfect tool for tech enthusiasts looking for the next level in gadgetry. Compact, powerful, and loaded with features."
}'
⏎
Product added/updated successfully.
```

### Creating an experiment

The shell script [outage-dynamodb-start.sh](./outage-dynamodb-start.sh) configures the Chaos API to cause faults within DynamoDB.
The configuration targets all operations in the DynamoDB service.
If required, you may filter specific operations such as `PutItem` or `GetItem`, but in this case we just want to cut off the database service completely.
This configuration will result in a 100% failure rate for all API calls to DynamoDB, each accompanied by an HTTP 500 status code with a `DatacentreNotFound` error.

When the script is run, the database becomes inaccessible not only for external clients but also for all services within LocalStack.
This means that service integrations can no longer retrieve or create new products.
API Gateway will return an Internal Server Error.
This is obviously problematic, but luckily, this potential issue has been caught early enough in the development phase, that the engineer can include proper error handling and a mechanism
that prevents data loss in case of an outage of the database.

![arch-2.png](images/arch-2.png)

At this point, we can try to make the architecture more resilient to such failures.
The solution includes an SNS topic, an SQS queue and a Lambda function that will pick up the queued element and retry the `PutItem` on the database.
In case DynamoDB is still unavailable, the item will be re-queued.

```text
$ curl --location 'http://12345.execute-api.localhost.localstack.cloud:4566/dev/productApi' \
    --header 'Content-Type: application/json' \
    --data '{
        "id": "prod-1003",
        "name": "Super Widget",
        "price": "29.99",
        "description": "A versatile widget that can be used for a variety of purposes. Durable, reliable, and affordable."
    }'
⏎
A DynamoDB error occurred. Message sent to queue.
```

Now this element sits in the queue, until the outage is over and the database is accessible again. 

The outage can be ended by running the shell script [outage-dynamodb-end.sh](./outage-dynamodb-end.sh).
Now, the Product element that initially has not reached the database, should reach its destination.
This can be verified by scanning the database:

```text
$ awslocal dynamodb scan --table-name Products
⏎
{
    "Items": [
        {
            "name": {
                "S": "Super Widget"
            },
            "description": {
                "S": "A versatile widget that can be used for a variety of purposes. Durable, reliable, and affordable."
            },
            "id": {
                "S": "prod-1003"
            },
            "price": {
                "N": "29.99"
            }
        },
        {
            "name": {
                "S": "Ultimate Gadget"
            },
            "description": {
                "S": "The Ultimate Gadget is the perfect tool for tech enthusiasts looking for the next level in gadgetry. Compact, powerful, and loaded with features."
            },
            "id": {
                "S": "prod-2004"
            },
            "price": {
                "N": "49.99"
            }
        }
    ],
    "Count": 2,
    "ScannedCount": 2,
    "ConsumedCapacity": null
}
```
