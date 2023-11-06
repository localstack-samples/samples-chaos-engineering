
# Product Managing Sample with API Gateway, Lambda, DynamoDB and FIS


| Environment      | <img src="https://img.shields.io/badge/LocalStack-deploys-4D29B4.svg?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAKgAAACoABZrFArwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAALbSURBVHic7ZpNaxNRFIafczNTGIq0G2M7pXWRlRv3Lusf8AMFEQT3guDWhX9BcC/uFAr1B4igLgSF4EYDtsuQ3M5GYrTaj3Tmui2SpMnM3PlK3m1uzjnPw8xw50MoaNrttl+r1e4CNRv1jTG/+v3+c8dG8TSilHoAPLZVX0RYWlraUbYaJI2IuLZ7KKUWCisgq8wF5D1A3rF+EQyCYPHo6Ghh3BrP8wb1en3f9izDYlVAp9O5EkXRB8dxxl7QBoNBpLW+7fv+a5vzDIvVU0BELhpjJrmaK2NMw+YsIxunUaTZbLrdbveZ1vpmGvWyTOJToNlsuqurq1vAdWPMeSDzwzhJEh0Bp+FTmifzxBZQBXiIKaAq8BBDQJXgYUoBVYOHKQRUER4mFFBVeJhAQJXh4QwBVYeHMQJmAR5GCJgVeBgiYJbg4T8BswYPp+4GW63WwvLy8hZwLcd5TudvBj3+OFBIeA4PD596nvc1iiIrD21qtdr+ysrKR8cY42itCwUP0Gg0+sC27T5qb2/vMunB/0ipTmZxfN//orW+BCwmrGV6vd63BP9P2j9WxGbxbrd7B3g14fLfwFsROUlzBmNM33XdR6Meuxfp5eg54IYxJvXCx8fHL4F3w36blTdDI4/0WREwMnMBeQ+Qd+YC8h4g78wF5D1A3rEqwBiT6q4ubpRSI+ewuhP0PO/NwcHBExHJZZ8PICI/e73ep7z6zzNPwWP1djhuOp3OfRG5kLROFEXv19fXP49bU6TbYQDa7XZDRF6kUUtEtoFb49YUbh/gOM7YbwqnyG4URQ/PWlQ4ASllNwzDzY2NDX3WwioKmBgeqidgKnioloCp4aE6AmLBQzUExIaH8gtIBA/lFrCTFB7KK2AnDMOrSeGhnAJSg4fyCUgVHsolIHV4KI8AK/BQDgHW4KH4AqzCQwEfiIRheKKUAvjuuu7m2tpakPdMmcYYI1rre0EQ1LPo9w82qyNziMdZ3AAAAABJRU5ErkJggg=="> |
|------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| __Services__     | Amazon API Gateway, Lambda, DynamoDB, SNS, SQS, FIS                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| __Categories__   | LocalStack Pro, Init Hooks, Java SDK                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |


## Description

In this example of utilizing AWS Fault Injection Simulator (FIS) to cause controlled outages to a DynamoDB database we will
demonstrate testing software behavior and error handling. This kind of test helps to ensure that the software can handle
database downtime gracefully by implementing strategies such as queuing requests to prevent data loss. This proactive error
handling ensures that the system can maintain its operations despite partial failures.

![fis-experiment-1](fis-experiment-1.png)

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
export LOCALSTACK_API_KEY = <your_localstack_api_key>
docker compose up
```

### Creating the resources

The resources are created via `init hooks` at startup, using the `init-resources.sh` file.

### Creating a Product

Using cURL we can create a Product entity:

```bash
curl --location 'http://12345.execute-api.localhost.localstack.cloud:4566/dev/productApi' \
--header 'Content-Type: application/json' \
--data '{
  "id": "prod-2004",
  "name": "Ultimate Gadget",
  "price": "49.99",
  "description": "The Ultimate Gadget is the perfect tool for tech enthusiasts looking for the next level in gadgetry. Compact, powerful, and loaded with features."
}
'

Product added/updated successfully.
```

### Creating an experiment

There's a file containing the experiment called `experiment-ddb.json`. This has a JSON configuration that will be utilized 
during the subsequent invocation of the `CreateExperimentTemplate` API.

```bash
 cat experiment-ddb.json
{
        "actions": {
                "Test action 1": {
                        "actionId": "localstack:generic:api-error",
                        "parameters": {
                                "service": "dynamodb",
                                "api": "all",
                                "percentage": "100",
                                "exception": "DynamoDbException",
                                "errorCode": "500"
                        }
                }
        },
        "description": "Template for interfering with the DynamoDB service",
        "stopConditions": [{
                "source": "none"
        }],
        "roleArn": "arn:aws:iam:000000000000:role/ExperimentRole"
}
```

Here we are targeting all APIs of the DynamoDb resource. Specific operations, such as `PutItem` or `GetItem` could also
be specified, but in this case, we just want to cut off the database completely. This configuration will result in a 100% failure rate
for all API calls, each accompanied by an HTTP 500 status code, with a DynamoDbException.

```bash
awslocal fis create-experiment-template --cli-input-json file://experiment-ddb.json
{
    "experimentTemplate": {
        "id": "895591e8-11e6-44c4-adc3-86592010562b",
        "description": "Template for interfering with the DynamoDB service",
        "actions": {
            "Test action 1": {
                "actionId": "localstack:generic:api-error",
                "parameters": {
                    "service": "dynamodb",
                    "api": "all",
                    "percentage": "100",
                    "exception": "DynamoDbException",
                    "errorCode": "500"
                }
            }
        },
        "stopConditions": [
            {
                "source": "none"
            }
        ],
        "creationTime": 1699308754.415716,
        "lastUpdateTime": 1699308754.415716,
        "roleArn": "arn:aws:iam:000000000000:role/ExperimentRole"
    }
}
```
We take note of the template ID for the next command:

```bash
 awslocal fis start-experiment --experiment-template-id 895591e8-11e6-44c4-adc3-86592010562b
{
    "experiment": {
        "id": "1b1238fd-316d-4956-93e7-5ada677a6f69",
        "experimentTemplateId": "895591e8-11e6-44c4-adc3-86592010562b",
        "roleArn": "arn:aws:iam:000000000000:role/ExperimentRole",
        "state": {
            "status": "running"
        },
        "actions": {
            "Test action 1": {
                "actionId": "localstack:generic:api-error",
                "parameters": {
                    "service": "dynamodb",
                    "api": "all",
                    "percentage": "100",
                    "exception": "DynamoDbException",
                    "errorCode": "500"
                }
            }
        },
        "stopConditions": [
            {
                "source": "none"
            }
        ],
        "creationTime": 1699308823.74327,
        "startTime": 1699308823.74327
    }
}
```

Now that the experiment is started, the database will be inaccessible, meaning the user can't get and can't post any new
product. The API Gateway will return an Internal Server Error. This is obviously problematic, but luckily, this potential issue
has been caught early enough in the development phase, that the engineer can include proper error handling and a mechanism
that prevents data loss in case of an outage of the database. This of course is not limited to DynamoDB, an outage can be 
simulated for any storage resource.


![fis-experiment-2](fis-experiment-2.png)

The solution includes an SNS topic, an SQS queue and a Lambda function that will pick up the queued element and retry the 
`PutItem` on the database. In case DynamoDB is still unavailable, the item will be re-queued.

```bash
curl --location 'http://12345.execute-api.localhost.localstack.cloud:4566/dev/productApi' \
                                                           --header 'Content-Type: application/json' \
                                                           --data '{
                                                         "id": "prod-1003",
                                                         "name": "Super Widget",
                                                         "price": "29.99",
                                                         "description": "A versatile widget that can be used for a variety of purposes. Durable, reliable, and affordable."
                                                       }
                                                       '
                                                       
A DynamoDB error occurred. Message sent to queue.⏎      
     
```

Now this element sits in the queue, until the outage is over. 
We can stop the experiment by using the following command:

```bash
 awslocal fis stop-experiment --id 1b1238fd-316d-4956-93e7-5ada677a6f69
{
    "experiment": {
        "id": "1b1238fd-316d-4956-93e7-5ada677a6f69",
        "experimentTemplateId": "895591e8-11e6-44c4-adc3-86592010562b",
        "roleArn": "arn:aws:iam:000000000000:role/ExperimentRole",
        "state": {
            "status": "stopped"
        },
        "actions": {
            "Test action 1": {
                "actionId": "localstack:generic:api-error",
                "parameters": {
                    "service": "dynamodb",
                    "api": "all",
                    "percentage": "100",
                    "exception": "DynamoDbException",
                    "errorCode": "500"
                },
                "startTime": 1699308823.750742,
                "endTime": 1699309736.259625
            }
        },
        "stopConditions": [
            {
                "source": "none"
            }
        ],
        "creationTime": 1699308823.74327,
        "startTime": 1699308823.74327,
        "endTime": 1699309736.259646
    }
}
```

The experiment ID comes from the prior used `start-experiment` command.
The experiment has been stopped, meaning that the Product that initially has not reached the database, has finally reached 
the destination. We can verify that by scanning the database:

```bash
awslocal dynamodb scan --table-name Products
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