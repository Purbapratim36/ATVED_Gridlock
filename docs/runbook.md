# Operational Runbook

## Deployment
ATVED is deployed via Kubernetes using horizontal scaling for the inference worker pool based on GPU allocation.
See `k8s/deployment.yaml`.

## Handling Kafka Backpressure
If the `inference_worker` consumer lag grows beyond threshold:
1. Increase worker replicas (ensure GPU node pool has capacity).
2. Tune `batch_size` in `BatchInferenceEngine` if GPU utilization < 80%.

## Checking Model Drift
Monitor Prometheus metrics at `atved_drift_feature_score`. Alerts fire > 0.15 Wasserstein distance.
Investigate camera feeds for physical changes (e.g., lens occlusion, new lighting).
