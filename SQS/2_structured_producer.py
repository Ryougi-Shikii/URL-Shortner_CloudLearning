
import boto3
import json
import uuid

sqs = boto3.client("sqs")

QUEUE_URL = sqs.get_queue_url(
    QueueName="producer-consumer-demo"
)["QueueUrl"]


        # "Process image.jpg",
        # "Process video.mp4",
        # "FAIL: Process corrupted image",
        # "Generate thumbnail.png",
        # "Compress document.pdf"

task = {
    "task_id": str(uuid.uuid4()),
    "operation": "generate_thumbnail",
    "file_name": "image.jpg",
    "user_id": "user-42"
}

response = sqs.send_message(
    QueueUrl=QUEUE_URL,

    # Actual message data
    MessageBody=json.dumps(task),

    # Additional metadata
    MessageAttributes={
        "Priority": {
            "StringValue": "High",
            "DataType": "String"
        },
        "Source": {
            "StringValue": "ImageService",
            "DataType": "String"
        },
        "Environment": {
            "StringValue": "Development",
            "DataType": "String"
        }
    }
)

print("Message sent!")
print("Message ID:", response["MessageId"])
print("Task ID:", task["task_id"])
