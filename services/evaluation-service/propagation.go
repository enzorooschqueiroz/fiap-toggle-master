package main

import (
	"context"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/sqs"
	"go.opentelemetry.io/otel"
)

// sqsAttrCarrier adapta MessageAttributes do SQS para propagation.TextMapCarrier,
// levando o contexto W3C (traceparent) até o analytics-service.
type sqsAttrCarrier map[string]*sqs.MessageAttributeValue

func (c sqsAttrCarrier) Get(key string) string {
	if v, ok := c[key]; ok && v.StringValue != nil {
		return *v.StringValue
	}
	return ""
}

func (c sqsAttrCarrier) Set(key, value string) {
	c[key] = &sqs.MessageAttributeValue{DataType: aws.String("String"), StringValue: aws.String(value)}
}

func (c sqsAttrCarrier) Keys() []string {
	keys := make([]string, 0, len(c))
	for k := range c {
		keys = append(keys, k)
	}
	return keys
}

func injectTraceContext(ctx context.Context) map[string]*sqs.MessageAttributeValue {
	carrier := sqsAttrCarrier{}
	otel.GetTextMapPropagator().Inject(ctx, carrier)
	return carrier
}
