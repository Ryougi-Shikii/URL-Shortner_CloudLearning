
import boto3
import json

sqs = boto3.client("sqs")

QUEUE_URL = sqs.get_queue_url(
    QueueName="idempotency-demo"
)["QueueUrl"]

task = {
    "task_id": "task-201",
    "operation": "process_payment",
    "amount": 500,
    "currency": "INR",
    "user_id": "user-42"
}

# Intentionally send the same business operation twice
for i in range(2):

    response = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(task)
    )

    print(f"Message {i + 1} sent")
    print("SQS Message ID:", response["MessageId"])

print("\nBoth messages sent.")
print("Business Task ID:", task["task_id"])
