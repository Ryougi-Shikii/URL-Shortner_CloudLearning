
# this is still just a atomic level idempotency
# if it crashes midway between task, look for it here: [4_resilient_...]

import boto3
import json
import time

from botocore.exceptions import ClientError

sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

QUEUE_URL = sqs.get_queue_url(
    QueueName="idempotency-demo"
)["QueueUrl"]

table = dynamodb.Table("processed-tasks")


def process_task(task):

    print("Processing payment...")
    print("Amount:", task["amount"])
    time.sleep(3)

    # Simulate successful business operation
    print("Payment processed successfully!")


def consume():

    response = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=5,
        WaitTimeSeconds=10
    )

    messages = response.get("Messages", [])

    if not messages:
        print("No messages available.")
        return

    for message in messages:

        task = json.loads(message["Body"])
        task_id = task["task_id"]

        print("\nReceived:", task_id)

        try:

            # Atomically claim this task
            table.put_item(
                Item={
                    "task_id": task_id,
                    "status": "PROCESSING"
                },
                ConditionExpression="attribute_not_exists(task_id)"
            )

            print("New task. Claim successful.")

            # Perform business operation
            process_task(task)

            # Mark task as completed
            table.update_item(
                Key={"task_id": task_id},
                UpdateExpression="SET #s = :status",
                ExpressionAttributeNames={
                    "#s": "status"
                },
                ExpressionAttributeValues={
                    ":status": "COMPLETED"
                }
            )

            print("Task marked COMPLETED.")

        except ClientError as error:

            if error.response["Error"]["Code"] == \
                    "ConditionalCheckFailedException":

                print("DUPLICATE DETECTED!")
                print("Skipping already claimed task.")

            else:
                raise

        # Delete successfully processed or duplicate messages
        sqs.delete_message(
            QueueUrl=QUEUE_URL,
            ReceiptHandle=message["ReceiptHandle"]
        )

        print("SQS message deleted.")


if __name__ == "__main__":
    consume()
