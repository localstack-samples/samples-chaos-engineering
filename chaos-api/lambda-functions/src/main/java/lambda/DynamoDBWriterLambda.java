package lambda;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashMap;
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.DynamoDbException;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;
import software.amazon.awssdk.services.dynamodb.model.PutItemResponse;

public class DynamoDBWriterLambda extends ProductApi implements RequestHandler<SQSEvent, Void> {

  private final ObjectMapper objectMapper = new ObjectMapper();

  private static final String TABLE_NAME = "Products";

  @Override
  public Void handleRequest(SQSEvent event, Context context) {

    for (SQSEvent.SQSMessage msg : event.getRecords()) {
      try {
        JsonNode rootNode = objectMapper.readTree(msg.getBody());
        String messageContent = rootNode.get("Message").asText();

        Map<String, String> productData;
        try {
          productData = objectMapper.readValue(messageContent, HashMap.class);
        } catch (JsonProcessingException e) {
          throw new RuntimeException(e);
        }
        HashMap<String, AttributeValue> itemValues = new HashMap<>();
        itemValues.put("id", AttributeValue.builder().s(productData.get("id")).build());
        itemValues.put("name", AttributeValue.builder().s(productData.get("name")).build());
        itemValues.put("price", AttributeValue.builder().n(productData.get("price")).build());
        itemValues.put("description",
            AttributeValue.builder().s(productData.get("description")).build());

        // Put the item into the DynamoDB table
        PutItemRequest putItemRequest = PutItemRequest.builder()
            .tableName(TABLE_NAME)
            .item(itemValues)
            .build();
        PutItemResponse putItemResult = ddb.putItem(putItemRequest);
        context.getLogger().log("Successfully processed message, result: " + putItemResult);

      } catch (DynamoDbException dbe) {
        // Service unavailable, let the message go back to the queue after visibility timeout
        context.getLogger().log(
            "DynamoDB service is unavailable, message will be retried. Error: "
                + dbe.getMessage());
        throw dbe;
      } catch (Exception e) {
        context.getLogger().log("Exception: Error processing the message: " + e.getMessage());
      }
    }
    return null;
  }

}
