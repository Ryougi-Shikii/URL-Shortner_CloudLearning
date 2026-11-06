
import boto3

QUEUE_URL = "http://localhost:4566/000000000000/producer-consumer-demo"

sqs = boto3.client(
    "sqs",
    endpoint_url="http://localhost:4566"
)


def process_message(body):
    """Simulate processing a task."""
    print(f"Processing: {body}")

    # Actual processing logic would go here.

    print(f"Successfully processed: {body}")


def consume_messages():
    print("Consumer started. Waiting for messages...\n")

    while True:
        response = sqs.receive_message(
            QueueUrl=QUEUE_URL,
            MaxNumberOfMessages=2,
            WaitTimeSeconds=10,
            VisibilityTimeout=30
        )

        messages = response.get("Messages", [])

        if not messages:
            print("No messages available. Waiting...")
            continue

        for message in messages:
            body = message["Body"]
            receipt_handle = message["ReceiptHandle"]

            try:
                process_message(body)

                sqs.delete_message(
                    QueueUrl=QUEUE_URL,
                    ReceiptHandle=receipt_handle
                )

                print("Message deleted from SQS.\n\n\n")

            except Exception as error:
                print(f"Processing failed: {error}")
                print("Message will become visible again after timeout.\n")


if __name__ == "__main__":
    try:
        consume_messages()
    except KeyboardInterrupt:
        print("\nConsumer stopped.")
