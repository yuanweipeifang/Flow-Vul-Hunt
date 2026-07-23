from app.ingestion.csv_reader import read_single_column_csv
from app.ingestion.payload_parser import parse_payload


def test_reads_headerless_single_column_csv() -> None:
    content = b'"GET /index?id=1 HTTP/1.1\\0D\\0AHost: example.test\\0D\\0A\\0D\\0A"\r\n'
    rows = read_single_column_csv(content, 10_000)
    assert len(rows) == 1
    parsed = parse_payload(rows[0])
    assert parsed.protocol == "http"
    assert parsed.http_method == "GET"
    assert parsed.host == "example.test"
    assert parsed.path == "/index"
    assert parsed.query == "id=1"
    assert parsed.parse_status == "success"


def test_binary_content_is_not_a_parse_failure() -> None:
    payload = "POST /binary HTTP/1.1\\0D\\0AContent-Type: application/octet-stream\\0D\\0A\\0D\\0A\\00\\FF\\01"
    parsed = parse_payload(payload)
    assert parsed.is_binary is True
    assert parsed.parse_status == "success"
    assert parsed.content_type == "application/octet-stream"

