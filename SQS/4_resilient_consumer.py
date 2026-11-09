
import boto3
import json
import time
import uuid
import sys

from botocore.exceptions import ClientError


# -------------------------------
# Configuration
# -------------------------------

sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

QUEUE_URL = sqs.get_queue_url(
    QueueName="idempotency-demo"
)["QueueUrl"]

tasks_table = dynamodb.Table("processed-tasks")
payments_table = dynamodb.Table("payments-ledger")

WORKER_ID = str(uuid.uuid4())

LEASE_SECONDS = 30
VISIBILITY_SECONDS = 40


# -------------------------------
# Step 1: Claim or recover task
# -------------------------------

def claim_task(task_id):

    now = int(time.time())
    lease_until = now + LEASE_SECONDS

    # Try creating a new task record
    try:

        tasks_table.put_item(
            Item={
                "task_id": task_id,
                "status": "PROCESSING",
                "worker_id": WORKER_ID,
                "lease_until": lease_until
            },
            ConditionExpression="attribute_not_exists(task_id)"
        )

        print("New task claimed.")
        return "CLAIMED"

    except ClientError as error:

        if error.response["Error"]["Code"] != \
                "ConditionalCheckFailedException":
            raise

    # Task already exists. Read its current state.
    result = tasks_table.get_item(
        Key={"task_id": task_id},
        ConsistentRead=True
    )

    item = result.get("Item")

    if not item:
        return "RETRY"

    if item["status"] == "COMPLETED":
        return "COMPLETED"

    # Another worker may still own this task.
    if item["lease_until"] > now:
        return "BUSY"

    # Existing lease expired. Attempt to reclaim.
    try:

        tasks_table.update_item(
            Key={"task_id": task_id},

            UpdateExpression=(
                "SET worker_id = :worker, "
                "lease_until = :lease"
            ),

            ConditionExpression=(
                "#status = :processing "
                "AND lease_until <= :now"
            ),

            ExpressionAttributeNames={
                "#status": "status"
            },

            ExpressionAttributeValues={
                ":worker": WORKER_ID,
                ":lease": lease_until,
                ":processing": "PROCESSING",
                ":now": now
            }
        )

        print("Expired task successfully reclaimed.")
        return "CLAIMED"

    except ClientError as error:

        if error.response["Error"]["Code"] == \
                "ConditionalCheckFailedException":
            return "BUSY"

        raise


# -------------------------------
# Step 2: Simulate business work
# -------------------------------


def renew_lease(task_id, receipt_handle):

    now = int(time.time())

    tasks_table.update_item(
        Key={"task_id": task_id},

        UpdateExpression="SET lease_until = :lease",

        ConditionExpression=(
            "#status = :processing "
            "AND worker_id = :worker "
            "AND lease_until >= :now"
        ),

        ExpressionAttributeNames={
            "#status": "status"
        },

        ExpressionAttributeValues={
            ":lease": now + LEASE_SECONDS,
            ":processing": "PROCESSING",
            ":worker": WORKER_ID,
            ":now": now
        }
    )

    sqs.change_message_visibility(
        QueueUrl=QUEUE_URL,
        ReceiptHandle=receipt_handle,
        VisibilityTimeout=VISIBILITY_SECONDS
    )

    print("Heartbeat: lease and visibility renewed.")



def process_business_operation(task, receipt_handle):

    print("Starting business operation...")

    print("Operation:", task["operation"])
    print("Amount:", task["amount"])

    # Simulate a longer-running operation.
    for step in range(1, 4):

        time.sleep(1)

        print(f"Processing stage {step}/3")

        # Renew ownership while working.
        renew_lease(
            task["task_id"],
            receipt_handle
        )

    # Optional crash simulation
    if "--crash-midway" in sys.argv:

        print("\nSIMULATING CONSUMER CRASH!")
        print("Business operation has not been committed.")

        sys.exit(1)

    print("Business operation preparation completed.")


# -------------------------------
# Step 3: Commit business result
# -------------------------------

def complete_task(task):

    task_id = task["task_id"]
    now = int(time.time())

    try:

        dynamodb.meta.client.transact_write_items(

            TransactItems=[

                {
                    "Put": {

                        "TableName": "payments-ledger",

                        "Item": {
                            "task_id": {"S": task_id},
                            "amount": {"N": str(task["amount"])},
                            "currency": {"S": task["currency"]},
                            "user_id": {"S": task["user_id"]},
                            "status": {"S": "PAID"}
                        },

                        "ConditionExpression":
                            "attribute_not_exists(task_id)"
                    }
                },

                {
                    "Update": {

                        "TableName": "processed-tasks",

                        "Key": {
                            "task_id": {"S": task_id}
                        },

                        "UpdateExpression": (
                            "SET #status = :completed, "
                            "completed_at = :time"
                        ),

                        "ConditionExpression": (
                            "#status = :processing "
                            "AND worker_id = :worker "
                            "AND lease_until >= :now"
                        ),

                        "ExpressionAttributeNames": {
                            "#status": "status"
                        },

                        "ExpressionAttributeValues": {
                            ":completed": {"S": "COMPLETED"},
                            ":processing": {"S": "PROCESSING"},
                            ":worker": {"S": WORKER_ID},
                            ":now": {"N": str(now)},
                            ":time": {"N": str(now)}
                        }
                    }
                }

            ]
        )

        print("Business result committed.")
        print("Task marked COMPLETED.")

        return True

    except ClientError as error:

        print("Transaction failed:", error)

        # Both transaction operations are rolled back.
        # The caller must not delete the SQS message.
        return False


# -------------------------------
# Step 4: Handle one SQS message
# -------------------------------

def consume():

    response = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=5,
        WaitTimeSeconds=10,
        VisibilityTimeout=VISIBILITY_SECONDS
    )

    messages = response.get("Messages", [])

    if not messages:
        print("No messages available.")
        return

    for message in messages:

        task = json.loads(message["Body"])
        task_id = task["task_id"]

        print("\n================================")
        print("Worker:", WORKER_ID)
        print("Task:", task_id)

        state = claim_task(task_id)

        # Already completed: safe to delete duplicate.
        if state == "COMPLETED":

            print("Task already completed. Skipping.")

            sqs.delete_message(
                QueueUrl=QUEUE_URL,
                ReceiptHandle=message["ReceiptHandle"]
            )

            continue

        # Another worker currently owns the task.
        if state == "BUSY":

            print("Task currently owned by another worker.")

            sqs.change_message_visibility(
                QueueUrl=QUEUE_URL,
                ReceiptHandle=message["ReceiptHandle"],
                VisibilityTimeout=LEASE_SECONDS
            )

            continue

        if state == "RETRY":

            print("Could not establish task ownership.")

            continue

        # We own the task now.
        try:

            process_business_operation(
                task,
                message["ReceiptHandle"]
            )

            success = complete_task(task)

            if not success:
                print("Commit failed. Keeping message for retry.")
                continue

            # Delete only after successful commit.
            sqs.delete_message(
                QueueUrl=QUEUE_URL,
                ReceiptHandle=message["ReceiptHandle"]
            )

            print("SQS message deleted.")

        except Exception as error:

            print("Processing failed:", error)

            # Release our lease for an earlier retry.
            try:

                tasks_table.update_item(
                    Key={"task_id": task_id},

                    UpdateExpression="SET lease_until = :zero",

                    ConditionExpression=(
                        "#status = :processing "
                        "AND worker_id = :worker"
                    ),

                    ExpressionAttributeNames={
                        "#status": "status"
                    },

                    ExpressionAttributeValues={
                        ":zero": 0,
                        ":processing": "PROCESSING",
                        ":worker": WORKER_ID
                    }
                )

            except ClientError:
                pass

            # Do not delete the message.
            # SQS will redeliver it.


if __name__ == "__main__":

    consume()
