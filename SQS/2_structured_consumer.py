
import boto3
import json

sqs = boto3.client("sqs")

QUEUE_URL = sqs.get_queue_url(
    QueueName="producer-consumer-demo"
)["QueueUrl"]

response = sqs.receive_message(
    QueueUrl=QUEUE_URL,
    MaxNumberOfMessages=5,
    WaitTimeSeconds=10,
    MessageAttributeNames=["All"]
)

messages = response.get("Messages", [])

if not messages:
    print("No messages available.")

for message in messages:

    # Decode structured JSON body
    task = json.loads(message["Body"])

    # Extract message attributes
    attributes = message.get("MessageAttributes", {})

    print("\n========== NEW TASK ==========")

    print("Task ID:", task["task_id"])
    print("Operation:", task["operation"])
    print("File:", task["file_name"])
    print("User:", task["user_id"])

    print("\n--- Message Attributes ---")

    for name, value in attributes.items():
        print(f"{name}: {value['StringValue']}")

    # Delete after successful processing
    sqs.delete_message(
        QueueUrl=QUEUE_URL,
        ReceiptHandle=message["ReceiptHandle"]
    )

    print("\nTask processed and deleted.")
