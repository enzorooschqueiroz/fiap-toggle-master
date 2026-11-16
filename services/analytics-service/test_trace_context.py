import os
from unittest import mock

os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_SQS_URL", "https://sqs.test/queue")
os.environ.setdefault("AWS_DYNAMODB_TABLE", "test-table")

with mock.patch("boto3.Session"), mock.patch("threading.Thread"):
    import app as analytics_app  # noqa: E402

from opentelemetry import trace  # noqa: E402

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
TRACEPARENT = f"00-{TRACE_ID}-00f067aa0ba902b7-01"
BODY = '{"user_id": "u1", "flag_name": "f1", "result": true, "timestamp": "2026-11-16T00:00:00Z"}'


def test_extract_with_traceparent():
    msg = {"MessageAttributes": {"traceparent": {"DataType": "String", "StringValue": TRACEPARENT}}}
    ctx = analytics_app.extract_context(msg)
    span_ctx = trace.get_current_span(ctx).get_span_context()
    assert format(span_ctx.trace_id, "032x") == TRACE_ID


def test_extract_without_attributes():
    ctx = analytics_app.extract_context({"MessageId": "1", "Body": BODY})
    assert not trace.get_current_span(ctx).get_span_context().is_valid


def test_process_message_without_attrs_still_saves():
    with mock.patch.object(analytics_app, "dynamodb_client") as ddb, \
         mock.patch.object(analytics_app, "sqs_client") as sqs:
        analytics_app.process_message({"MessageId": "1", "ReceiptHandle": "r", "Body": BODY})
    ddb.put_item.assert_called_once()
    sqs.delete_message.assert_called_once()
