package lambda;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.APIGatewayProxyRequestEvent;
import com.amazonaws.services.lambda.runtime.events.APIGatewayProxyResponseEvent;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashMap;
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.DynamoDbException;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.GetItemResponse;

public class GetProduct extends ProductApi implements
    RequestHandler<APIGatewayProxyRequestEvent, APIGatewayProxyResponseEvent> {

  private static final String TABLE_NAME = "Products";
  private static final String PRODUCT_ID = "id";
  private final ObjectMapper objectMapper = new ObjectMapper();


  @Override
  public APIGatewayProxyResponseEvent handleRequest(APIGatewayProxyRequestEvent requestEvent,
      Context context) {
    String productId = requestEvent.getQueryStringParameters().get(PRODUCT_ID);
    System.out.println(requestEvent);
    System.out.println("PRODUCT ID: " + productId);

    HashMap<String, AttributeValue> valueMap = new HashMap<>();
    valueMap.put("id", AttributeValue.fromS(productId));

    GetItemRequest getItemRequest = GetItemRequest.builder()
        .tableName(TABLE_NAME)
        .key(valueMap)
        .build();

    try {
      GetItemResponse getItemResponse = ddb.getItem(getItemRequest);
      if (getItemResponse.item() != null && !getItemResponse.item().isEmpty()) {
        // Convert the result to JSON format

        Map<String, Object> responseBody = new HashMap<>();
        getItemResponse.item().forEach((k, v) -> responseBody.put(k, convertAttributeValue(v)));

        return new APIGatewayProxyResponseEvent().withStatusCode(200)
            .withBody(objectMapper.writeValueAsString(responseBody));
      } else {
        return new APIGatewayProxyResponseEvent().withStatusCode(404).withBody("Product not found");
      }
    } catch (DynamoDbException | JsonProcessingException e) {
      context.getLogger().log("Error: " + e.getMessage());
      return new APIGatewayProxyResponseEvent().withStatusCode(500)
          .withBody("Internal server error");
    }
  }

  private Object convertAttributeValue(AttributeValue value) {
    if (value.s() != null) {
      return value.s();
    }
    if (value.n() != null) {
      return value.n();
    }
    if (value.b() != null) {
      return value.b();
    }
    return null;
  }
}