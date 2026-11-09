
import boto3

QUEUE_URL = "http://localhost:4566/000000000000/producer-consumer-demo"

sqs = boto3.client(
    "sqs",
    endpoint_url="http://localhost:4566"
)

def send_task(task):
    response = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=task
    ) 

    print(f"Sent: {task}")
    print(f"Message ID: {response['MessageId']}")
    print("-" * 40)


if __name__ == "__main__":
    tasks = [
        "Process image.jpg",
        "Process video.mp4",
        "FAIL: Process corrupted image",
        "Generate thumbnail.png",
        "Compress document.pdf"
    ]

    for task in tasks:
        send_task(task)
