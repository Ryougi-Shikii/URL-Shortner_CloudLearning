
import boto3
import json

sqs = boto3.client("sqs")

QUEUE_URL = sqs.get_queue_url(
    QueueName="idempotency-demo"
)["QueueUrl"]

# Same task ID for both messages
task = {
    "task_id": "task-101",
    "operation": "process_payment",
    "amount": 500
}

# Intentionally send the same task twice
for i in range(2):

    response = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(task)
    )

    print(f"Message {i + 1} sent!")
    print("Message ID:", response["MessageId"])
    print("Task ID:", task["task_id"])
    print("-" * 40)
