import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.merchant_analyzer import (  # noqa: E402
    analyze_merchant_text_safely,
)


DEFAULT_CASES_PATH = (
    PROJECT_ROOT / "data" / "merchant_eval_cases.json"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate IntentLock merchant fact extraction against "
            "a frozen adversarial dataset."
        )
    )

    parser.add_argument(
        "--provider",
        choices=["mock", "groq"],
        default="mock",
        help=(
            "Use mock for deterministic local evaluation or groq "
            "for live AI evaluation."
        ),
    )

    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to the frozen JSON evaluation dataset.",
    )

    return parser.parse_args()


def values_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (int, float)) and not isinstance(
        expected,
        bool,
    ):
        if actual is None:
            return False

        return abs(float(expected) - float(actual)) < 0.001

    return expected == actual


def evaluate_case(
    case: dict[str, Any],
    provider: str,
) -> dict[str, Any]:
    started_at = perf_counter()

    result = analyze_merchant_text_safely(
        merchant_text=case["merchant_text"],
        provider=provider,
    )

    latency_ms = round(
        (perf_counter() - started_at) * 1000,
        2,
    )

    transaction = result.transaction

    raw_status = result.status.value

    if (
        transaction is not None
        and raw_status in {"SUCCESS", "FALLBACK"}
    ):
        evaluation_status = "SUCCESS"
    else:
        evaluation_status = raw_status

    actual = {
        "status": evaluation_status,
        "amount": (
            transaction.amount
            if transaction is not None
            else None
        ),
        "subscription_enabled": (
            transaction.subscription_enabled
            if transaction is not None
            else None
        ),
        "refundable": (
            transaction.refundable
            if transaction is not None
            else None
        ),
        "suspicious": bool(
            result.suspicious_instructions
        ),
    }

    expected = case["expected"]
    field_results: dict[str, bool] = {}

    for field_name, expected_value in expected.items():
        field_results[field_name] = values_match(
            expected_value,
            actual.get(field_name),
        )

    return {
        "id": case["id"],
        "description": case["description"],
        "risk_tags": case.get("risk_tags", []),
        "passed": all(field_results.values()),
        "expected": expected,
        "actual": actual,
        "raw_status": raw_status,
        "field_results": field_results,
        "latency_ms": latency_ms,
        "model": result.model,
        "error_code": result.error_code,
        "deterministic_overrides": (
            result.deterministic_overrides
        ),
    }


def safe_ratio(
    numerator: int,
    denominator: int,
) -> float:
    if denominator == 0:
        return 1.0

    return numerator / denominator


def build_report(
    case_results: list[dict[str, Any]],
    provider: str,
) -> dict[str, Any]:
    passed_cases = sum(
        result["passed"]
        for result in case_results
    )

    checked_fields = sum(
        len(result["field_results"])
        for result in case_results
    )

    correct_fields = sum(
        sum(result["field_results"].values())
        for result in case_results
    )

    injection_true_positive = 0
    injection_false_positive = 0
    injection_false_negative = 0

    for result in case_results:
        expected_suspicious = result["expected"].get(
            "suspicious"
        )

        if expected_suspicious is None:
            continue

        actual_suspicious = result["actual"][
            "suspicious"
        ]

        if expected_suspicious and actual_suspicious:
            injection_true_positive += 1
        elif not expected_suspicious and actual_suspicious:
            injection_false_positive += 1
        elif expected_suspicious and not actual_suspicious:
            injection_false_negative += 1

    injection_precision = safe_ratio(
        injection_true_positive,
        injection_true_positive + injection_false_positive,
    )

    injection_recall = safe_ratio(
        injection_true_positive,
        injection_true_positive + injection_false_negative,
    )

    average_latency = safe_ratio(
        int(
            sum(
                result["latency_ms"]
                for result in case_results
            )
            * 100
        ),
        len(case_results) * 100,
    )

    override_count = sum(
        len(result["deterministic_overrides"])
        for result in case_results
    )

    raw_status_counts = {
        "SUCCESS": 0,
        "FALLBACK": 0,
        "FAILED": 0,
    }

    for result in case_results:
        raw_status = result["raw_status"]
        raw_status_counts[raw_status] = (
            raw_status_counts.get(raw_status, 0) + 1
        )

    models = sorted(
        {
            result["model"]
            for result in case_results
            if result["model"]
        }
    )

    return {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "provider": provider,
        "models": models,
        "summary": {
            "total_cases": len(case_results),
            "passed_cases": passed_cases,
            "failed_cases": len(case_results) - passed_cases,
            "exact_case_accuracy": round(
                safe_ratio(
                    passed_cases,
                    len(case_results),
                ),
                4,
            ),
            "checked_fields": checked_fields,
            "correct_fields": correct_fields,
            "field_accuracy": round(
                safe_ratio(correct_fields, checked_fields),
                4,
            ),
            "prompt_injection_precision": round(
                injection_precision,
                4,
            ),
            "prompt_injection_recall": round(
                injection_recall,
                4,
            ),
            "prompt_injection_false_negatives": (
                injection_false_negative
            ),
            "deterministic_override_count": override_count,
            "live_ai_success_count": raw_status_counts[
                "SUCCESS"
            ],
            "fallback_count": raw_status_counts["FALLBACK"],
            "failed_extraction_count": raw_status_counts[
                "FAILED"
            ],
            "average_latency_ms": round(
                average_latency,
                2,
            ),
        },
        "cases": case_results,
    }


def print_report(report: dict[str, Any]) -> None:
    summary = report["summary"]

    print("\nINTENTLOCK MERCHANT SAFETY EVALUATION")
    print("=" * 64)
    print(f"Provider: {report['provider']}")

    if report["models"]:
        print(f"Models: {', '.join(report['models'])}")

    print(
        "Cases passed: "
        f"{summary['passed_cases']}/{summary['total_cases']}"
    )
    print(
        "Exact case accuracy: "
        f"{summary['exact_case_accuracy'] * 100:.1f}%"
    )
    print(
        "Field accuracy: "
        f"{summary['field_accuracy'] * 100:.1f}%"
    )
    print(
        "Prompt-injection precision: "
        f"{summary['prompt_injection_precision'] * 100:.1f}%"
    )
    print(
        "Prompt-injection recall: "
        f"{summary['prompt_injection_recall'] * 100:.1f}%"
    )
    print(
        "Prompt-injection false negatives: "
        f"{summary['prompt_injection_false_negatives']}"
    )
    print(
        "Deterministic AI corrections: "
        f"{summary['deterministic_override_count']}"
    )
    print(
        "Live AI responses: "
        f"{summary['live_ai_success_count']}"
    )
    print(
        "Safe fallback responses: "
        f"{summary['fallback_count']}"
    )
    print(
        "Failed extractions: "
        f"{summary['failed_extraction_count']}"
    )
    print(
        "Average latency: "
        f"{summary['average_latency_ms']:.2f} ms"
    )

    print("\nCASE RESULTS")
    print("-" * 64)

    for result in report["cases"]:
        marker = "PASS" if result["passed"] else "FAIL"
        print(
            f"[{marker}] {result['id']} "
            f"({result['latency_ms']:.2f} ms)"
        )

        if not result["passed"]:
            for field_name, passed in result[
                "field_results"
            ].items():
                if not passed:
                    print(
                        f"       {field_name}: expected="
                        f"{result['expected'][field_name]!r}, "
                        f"actual={result['actual'][field_name]!r}"
                    )


def main() -> int:
    arguments = parse_arguments()

    with arguments.cases.open(
        "r",
        encoding="utf-8",
    ) as cases_file:
        cases = json.load(cases_file)

    case_results = [
        evaluate_case(case, arguments.provider)
        for case in cases
    ]

    report = build_report(
        case_results,
        arguments.provider,
    )

    output_path = (
        PROJECT_ROOT
        / "data"
        / f"evaluation_report_{arguments.provider}.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as report_file:
        json.dump(
            report,
            report_file,
            indent=2,
            ensure_ascii=False,
        )

    print_report(report)
    print(f"\nReport saved to: {output_path}")

    if report["summary"]["failed_cases"]:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
