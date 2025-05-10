awslocal sns create-topic --name ProductEventsTopic

awslocal sqs create-queue --queue-name ProductEventsQueue

awslocal sqs get-queue-attributes --queue-url http://localhost:4566/000000000000/ProductEventsQueue --attribute-names QueueArn

awslocal sns subscribe \
    --topic-arn arn:aws:sns:us-east-1:000000000000:ProductEventsTopic \
    --protocol sqs \
    --notification-endpoint arn:aws:sqs:us-east-1:000000000000:ProductEventsQueue

awslocal lambda create-function \
  --function-name process-product-events \
  --runtime java17 \
  --handler lambda.DynamoDBWriterLambda::handleRequest \
  --memory-size 1024 \
  --timeout 20 \
  --zip-file fileb://lambda-functions/target/product-lambda.jar \
  --role arn:aws:iam::000000000000:role/productRole

awslocal lambda create-event-source-mapping \
    --function-name process-product-events \
    --batch-size 10 \
    --event-source-arn arn:aws:sqs:us-east-1:000000000000:ProductEventsQueue

awslocal sqs set-queue-attributes \
    --queue-url http://localhost:4566/000000000000/ProductEventsQueue \
    --attributes VisibilityTimeout=10
