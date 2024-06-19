package lambda;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.APIGatewayProxyRequestEvent;
import com.amazonaws.services.lambda.runtime.events.APIGatewayProxyResponseEvent;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonMappingException;
import java.util.HashMap;
import java.util.Map;
import software.amazon.awssdk.awscore.exception.AwsServiceException;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;
import software.amazon.awssdk.services.dynamodb.model.DynamoDbException;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;
import software.amazon.awssdk.services.sns.model.PublishRequest;

public class AddProduct extends ProductApi implements
    RequestHandler<APIGatewayProxyRequestEvent, APIGatewayProxyResponseEvent> {

  private static final String TABLE_NAME = "Products";
  private static final String PRODUCT_ID = "id";

  @Override
  public APIGatewayProxyResponseEvent handleRequest(APIGatewayProxyRequestEvent requestEvent,
      Context context) {

    Map<String, String> productData;
    try {
      productData = objectMapper.readValue(requestEvent.getBody(), HashMap.class);
    } catch (JsonMappingException e) {
      throw new RuntimeException(e);
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new RuntimeException(e);
    }

    HashMap<String, AttributeValue> itemValues = new HashMap<>();
    itemValues.put("id", AttributeValue.builder().s(productData.get("id")).build());
    itemValues.put("name", AttributeValue.builder().s(productData.get("name")).build());
    itemValues.put("price", AttributeValue.builder().n(productData.get("price")).build());
    itemValues.put("description",
        AttributeValue.builder().s(productData.get("description")).build());

    PutItemRequest putItemRequest = PutItemRequest.builder()
        .tableName(TABLE_NAME)
        .item(itemValues)
        .conditionExpression("attribute_not_exists(id) OR id = :id")
        .expressionAttributeValues(
            Map.of(":id", AttributeValue.builder().s(productData.get("id")).build()))
        .build();

    Map<String, String> headers = new HashMap<>();
    headers.put("Content-Type", "application/json");

    try {
      ddb.putItem(putItemRequest);
      return new APIGatewayProxyResponseEvent().withStatusCode(200)
          .withBody("Product added/updated successfully.")
          .withIsBase64Encoded(false).withHeaders(headers);
    } catch (ConditionalCheckFailedException e) {
      return new APIGatewayProxyResponseEvent().withStatusCode(409)
          .withBody("Product with the given ID already exists.")
          .withIsBase64Encoded(false).withHeaders(headers);
    } catch (DynamoDbException e) {
      context.getLogger().log("Error: " + e.getMessage());
      // Publish message to SNS topic if DynamoDB operation fails.
      String productDataJson;
      try {
        productDataJson = objectMapper.writeValueAsString(productData);
      } catch (JsonProcessingException ex) {
        throw new RuntimeException(ex);
      }
      PublishRequest publishRequest = PublishRequest.builder()
          .message(productDataJson)
          .topicArn(topicArn)
          .build();
      context.getLogger().log("Sending to queue: " + productDataJson);

      snsClient.publish(publishRequest);

      return new APIGatewayProxyResponseEvent().withStatusCode(200)
          .withBody("A DynamoDB error occurred. Message sent to queue.")
          .withIsBase64Encoded(false).withHeaders(headers);
    } catch (AwsServiceException ex) {
      context.getLogger().log("AwsServiceException exception: " + ex.getMessage());
      return new APIGatewayProxyResponseEvent().withStatusCode(500)
          .withBody(ex.getMessage())
          .withIsBase64Encoded(false).withHeaders(headers);
    } catch (RuntimeException e) {
      context.getLogger().log("Runtime exception: " + e.getMessage());
      return new APIGatewayProxyResponseEvent().withStatusCode(500)
          .withBody(e.getMessage())
          .withIsBase64Encoded(false).withHeaders(headers);
    } catch (Exception e) {
      context.getLogger().log("Generic exception: " + e.getMessage());
      return new APIGatewayProxyResponseEvent().withStatusCode(500)
          .withBody(e.getMessage())
          .withIsBase64Encoded(false).withHeaders(headers);
    }

  }
}