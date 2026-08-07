from app.repositories.telemetry import BUCKET_SECONDS, METRIC_COLUMNS


def test_metric_columns_are_allowlisted() -> None:
    assert set(METRIC_COLUMNS) == {
        "latency",
        "throughput",
        "cpuUsage",
        "memoryUsage",
        "errorRate",
        "payloadSize",
    }


def test_bucket_sizes_match_contract() -> None:
    assert BUCKET_SECONDS == {"raw": None, "1m": 60, "5m": 300, "1h": 3600}
