package dynamodb_streams;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.DynamodbEvent;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.DynamoDbException;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;
import software.amazon.awssdk.services.dynamodb.model.PutItemResponse;

import java.net.URI;
import java.util.HashMap;
import java.util.Map;

public class DynamoDBStreamHandler implements RequestHandler<DynamodbEvent, String> {

    protected static final String LOCALSTACK_HOSTNAME = System.getenv("LOCALSTACK_HOSTNAME");

    private static final String TARGET_TABLE_NAME = "Products";
    private static final Region TARGET_REGION = Region.EU_CENTRAL_1;
    private static final DynamoDbClient DDB = DynamoDbClient.builder()
            .region(TARGET_REGION)
            .endpointOverride(URI.create(String.format("http://%s:4566", LOCALSTACK_HOSTNAME)))
            .credentialsProvider(
                    StaticCredentialsProvider.create(AwsBasicCredentials.create("test", "test")))
            .build();

    @Override
    public String handleRequest(DynamodbEvent ddbEvent, Context context) {
        for (DynamodbEvent.DynamodbStreamRecord record : ddbEvent.getRecords()) {
            if (record.getEventName().equals("INSERT") || record.getEventName().equals("MODIFY")) {
                try {
                    // Convert stream record to a DynamoDB PutItemRequest
                    PutItemRequest putItemRequest = createPutItemRequest(record.getDynamodb().getNewImage());
                    PutItemResponse putItemResponse = DDB.putItem(putItemRequest);
                    context.getLogger().log("PutItem succeeded: " + putItemResponse.toString());

                } catch (DynamoDbException e) {
                    context.getLogger().log("Error putting item to TargetTable: " + e.getMessage());
                }
            }
        }
        return "Successfully processed " + ddbEvent.getRecords().size() + " records.";
    }

    private PutItemRequest createPutItemRequest(Map<String, com.amazonaws.services.lambda.runtime.events.models.dynamodb.AttributeValue> newImage) {

        HashMap<String, AttributeValue> item = new HashMap<>();
        item.put("id", AttributeValue.builder().s(newImage.get("id").getS()).build());
        item.put("name", AttributeValue.builder().s(newImage.get("name").getS()).build());
        item.put("price", AttributeValue.builder().n(newImage.get("price").getN()).build());
        item.put("description",
                AttributeValue.builder().s(newImage.get("description").getS()).build());

        return PutItemRequest.builder()
                .tableName(TARGET_TABLE_NAME)
                .item(item)
                .build();
    }

}
