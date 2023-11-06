package lambda;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.sns.SnsClient;

public class ProductApi {

  protected static final String LOCALSTACK_HOSTNAME = System.getenv("LOCALSTACK_HOSTNAME");
  protected static final String AWS_REGION = System.getenv("AWS_REGION");
  protected static final String topicArn = "arn:aws:sns:us-east-1:000000000000:ProductEventsTopic";
  protected ObjectMapper objectMapper = new ObjectMapper();

  protected SnsClient snsClient = SnsClient.builder()
      .endpointOverride(URI.create(String.format("http://%s:4566", LOCALSTACK_HOSTNAME)))
      .credentialsProvider(
          StaticCredentialsProvider.create(AwsBasicCredentials.create("test", "test")))
      .region(Region.of(AWS_REGION))
      .build();

  protected DynamoDbClient ddb = DynamoDbClient.builder()
      .endpointOverride(URI.create(String.format("http://%s:4566", LOCALSTACK_HOSTNAME)))
      .credentialsProvider(
          StaticCredentialsProvider.create(AwsBasicCredentials.create("test", "test")))
      .region(Region.of(AWS_REGION))
      .endpointDiscoveryEnabled(true)
      .build();
}
