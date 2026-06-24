"""运行 RCA 演示 - 对示例异常事件执行 RCA 分析。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.agent.workflow import RCAWorkflow
from app.schemas.api import AnomalyEvent


def load_sample_events() -> list[dict]:
    """加载示例异常事件。"""
    events_path = Path(__file__).parent.parent / "data" / "samples" / "anomaly_events.json"
    with open(events_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    print("运行演示前请确认已执行 db/001_init_app_schema.sql 和 db/002_init_business_schema.sql 并插入示例数据。")

    # 加载示例事件
    events = load_sample_events()
    print(f"加载了 {len(events)} 个示例异常事件\n")

    workflow = RCAWorkflow()

    for i, event_data in enumerate(events, 1):
        print(f"{'='*60}")
        print(f"  [{i}/{len(events)}] 分析异常: {event_data['anomaly_type']}")
        print(f"  描述: {event_data['description'][:60]}...")
        print(f"{'='*60}")

        event = AnomalyEvent(**event_data)

        try:
            state = workflow.run(event=event)

            print(f"\n  结果:")
            print(f"    任务 ID: {state.task_id}")
            print(f"    状态: {state.status.value}")
            print(f"    置信度: {state.confidence:.0%}")
            print(f"    反思轮次: {state.reflection_round}")

            if state.final_report:
                report = state.final_report
                print(f"    根因: {report.get('root_cause', 'N/A')[:80]}")
                print(f"    分类: {report.get('root_cause_category', 'N/A')}")
                recs = report.get('recommendations', [])
                if recs:
                    print(f"    建议 ({len(recs)} 条):")
                    for rec in recs[:3]:
                        print(f"      - {rec}")

            # 打印假设评估
            confirmed = [h for h in state.hypotheses if h.get("status") == "confirmed"]
            if confirmed:
                print(f"\n  已确认假设:")
                for h in confirmed:
                    print(f"    [{h['id']}] {h['description'][:60]} (概率: {h['probability']:.0%})")

        except Exception as e:
            print(f"\n  分析失败: {e}")

        print()

    print("演示完成!")


if __name__ == "__main__":
    main()
