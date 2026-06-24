"""Reranker 模型重排测试。"""
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _candidates() -> list[dict]:
    return [
        {
            "id": "doc_a",
            "title": "MES-WMS 接口超时处理",
            "content": "接口 Timeout 时检查网络、重试策略和库存同步延迟。",
            "hybrid_score": 0.9,
        },
        {
            "id": "doc_b",
            "title": "WS-05 设备维保与排程冲突",
            "content": "WS-05 主轴精度偏差且刀库故障，多个高优先级工单等待，导致排程冲突风险。",
            "hybrid_score": 0.6,
        },
    ]


def _enable_ollama_reranker(monkeypatch, reranker_module) -> None:
    monkeypatch.setattr(reranker_module.settings, "reranker_provider", "ollama")
    monkeypatch.setattr(reranker_module.settings, "reranker_model", "test-reranker")
    monkeypatch.setattr(reranker_module.settings, "reranker_base_url", "http://localhost:11434")
    monkeypatch.setattr(reranker_module.settings, "reranker_api_key", "ollama")


def _mock_yes_no_post(monkeypatch, reranker_module, outputs: list[str]) -> Mock:
    responses = []
    for content in outputs:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": content}
        responses.append(response)
    post = Mock(side_effect=responses)
    monkeypatch.setattr(reranker_module.httpx, "post", post)
    return post


def test_reranker_uses_configured_model_when_available(monkeypatch):
    """配置模型可用时，应按 RERANKER_MODEL 的 yes/no 判断顺序重排。"""
    import app.rag.reranker as reranker_module
    from app.rag.reranker import Reranker

    _enable_ollama_reranker(monkeypatch, reranker_module)
    post = _mock_yes_no_post(monkeypatch, reranker_module, ["no", "yes"])

    results = Reranker().rerank("WS-05 设备维保导致排程延迟", _candidates())

    assert [item["id"] for item in results] == ["doc_b", "doc_a"]
    assert results[0]["rerank_score"] == 0.9
    assert results[0]["rerank_reason"] == "模型判断候选与查询相关"
    assert post.call_count == 2


def test_reranker_scores_each_candidate_with_yes_no_model(monkeypatch):
    """Reranker 模型应按 query-document 逐条 yes/no 评分，而不是要求生成 JSON 数组。"""
    import app.rag.reranker as reranker_module
    from app.rag.reranker import Reranker

    _enable_ollama_reranker(monkeypatch, reranker_module)
    post = _mock_yes_no_post(monkeypatch, reranker_module, ["no", "yes"])

    results = Reranker().rerank("WS-05 设备维保导致排程延迟", _candidates())

    assert [item["id"] for item in results] == ["doc_b", "doc_a"]
    assert results[0]["rerank_score"] == 0.9
    assert results[0]["rerank_reason"] == "模型判断候选与查询相关"
    assert post.call_count == 2
    prompts = [call.kwargs["json"]["prompt"] for call in post.call_args_list]
    assert all("answer can only be yes or no" in prompt.lower() for prompt in prompts)
    assert all("Output JSON array only" not in prompt for prompt in prompts)


def test_reranker_falls_back_to_rules_when_model_fails(monkeypatch):
    """模型调用失败时，仍应返回规则重排结果。"""
    import app.rag.reranker as reranker_module
    from app.rag.reranker import Reranker

    _enable_ollama_reranker(monkeypatch, reranker_module)
    monkeypatch.setattr(reranker_module.httpx, "post", Mock(side_effect=RuntimeError("model down")))

    results = Reranker().rerank("接口 Timeout 库存同步", _candidates())

    assert [item["id"] for item in results] == ["doc_a", "doc_b"]
    assert "rerank_score" in results[0]


def test_reranker_parses_first_valid_json_array_from_verbose_model_output():
    """模型输出夹杂解释文本和重复 JSON 时，应提取第一段有效 JSON 数组。"""
    from app.rag.reranker import Reranker

    verbose_output = """
    思考过程文本。
    [{"id": "doc_b", "score": 0.93, "reason": "最相关"}]
    额外解释文本。
    [{"id": "doc_a", "score": 0.10, "reason": "不相关"}]
    """

    ranked = Reranker()._parse_ranked_items(verbose_output)

    assert ranked == [{"id": "doc_b", "score": 0.93, "reason": "最相关"}]
