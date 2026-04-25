from app.ui.json_extract import maybe_extract_valid_json_text


def test_maybe_extract_valid_json_text_extracts_first_valid_json_from_noisy_response():
    raw = '설명입니다.\n{"name":"demo","scripts":{"dev":"vite"}}\n추가 설명'
    out = maybe_extract_valid_json_text(raw)
    assert out == '{"name":"demo","scripts":{"dev":"vite"}}'


def test_maybe_extract_valid_json_text_keeps_non_json_text_unchanged():
    raw = 'public class Demo {}'
    out = maybe_extract_valid_json_text(raw)
    assert out == raw
