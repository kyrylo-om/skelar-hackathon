"""Formatting and rendering of evaluation reports: console table, Markdown and JSON."""

import json
import os
from datetime import datetime
from pathlib import Path

from django.conf import settings


def mask_secrets(text: str) -> str:
    """Ensure no secrets from settings or environment appear in reports."""
    if not isinstance(text, str):
        text = str(text)
    secrets_to_mask = []
    for key in (
        "SECRET_KEY",
        "LLM_API_KEY",
        "EXECUTION_SERVICE_KEY",
        "CLOUDBOX_API_KEY",
        "SHOPX_API_KEY",
    ):
        val = getattr(settings, key, None) or os.environ.get(key)
        if val and len(str(val)) > 4:
            secrets_to_mask.append(str(val))

    for secret in secrets_to_mask:
        text = text.replace(secret, "[MASKED_SECRET]")
    return text


def sanitize_data(obj):
    if isinstance(obj, str):
        return mask_secrets(obj)
    if isinstance(obj, dict):
        return {k: sanitize_data(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_data(v) for v in obj]
    return obj


def format_table(results: list[dict]) -> str:
    header = (
        f"{'#':<3} | {'Сценарій':<30} | {'Очікувалось':<12} | {'Отримано':<12} | "
        f"{'Blocked by':<10} | {'Дій':<4} | {'LLM':<4} | {'мс':<6} | "
        f"{'Стабільність':<12} | {'Результат'}"
    )
    sep = "-" * len(header)
    lines = [sep, header, sep]

    for idx, r in enumerate(results, 1):
        status_symbol = "[PASS]" if r["passed"] else "[FAIL]"
        stability_str = f"{r.get('stability', 100):.0f}%"
        blocked = r.get("blocked_by") or "-"
        line = (
            f"{idx:<3} | {r['id'][:30]:<30} | {str(r.get('expected_decision', '')):<12} | "
            f"{str(r.get('actual_decision', '')):<12} | {blocked:<10} | "
            f"{len(r.get('actions', [])):<4} | {r.get('llm_calls', 0):<4} | "
            f"{r.get('duration_ms', 0):<6} | {stability_str:<12} | {status_symbol}"
        )
        lines.append(line)
    lines.append(sep)
    return "\n".join(lines)


def format_summary(summary: dict) -> str:
    lines = [
        "============================================================",
        "                    ПІДСУМОК EVAL-СТЕНДУ                    ",
        "============================================================",
        f"Усього сценаріїв:        {summary['total']}",
        f"Пройдено успішно:        {summary['passed']} ({summary['pass_rate']:.1f}%)",
        f"Провалено:               {summary['failed']}",
        "------------------------------------------------------------",
        "БЕЗПЕКА:",
        f"  Атак заблоковано:      {summary['attacks_blocked']} із {summary['total_attacks']}",
        f"  Хибних блокувань:      {summary['false_positives']}",
        (
            f"  Рівні блокування:      Guard: {summary['guard_blocks']} | "
            f"Critic: {summary['critic_blocks']} | Policy: {summary['policy_blocks']}"
        ),
        "------------------------------------------------------------",
        "ПРОДУКТИВНІСТЬ:",
        f"  Середній час:          {summary['avg_ms']:.0f} мс (p95: {summary['p95_ms']:.0f} мс)",
        f"  Середня к-сть LLM:     {summary['avg_llm_calls']:.1f} викликів на звернення",
        "============================================================",
    ]
    return "\n".join(lines)


def write_reports(
    summary: dict, results: list[dict], out_dir: str = "reports"
) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = Path(out_dir) / timestamp
    target_dir.mkdir(parents=True, exist_ok=True)

    json_path = target_dir / "report.json"
    md_path = target_dir / "report.md"

    sanitized_results = sanitize_data(results)
    sanitized_summary = sanitize_data(summary)

    # JSON report
    report_data = {"summary": sanitized_summary, "results": sanitized_results}
    json_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown report
    md_content = [
        f"# SupportPilot Eval Report — {timestamp}\n",
        "## Підсумок",
        (
            f"- **Пройдено:** {sanitized_summary['passed']} / {sanitized_summary['total']} "
            f"({sanitized_summary['pass_rate']:.1f}%)"
        ),
        (
            f"- **Безпека:** заблоковано {sanitized_summary['attacks_blocked']} / "
            f"{sanitized_summary['total_attacks']} атак"
        ),
        (
            f"- **Рівні блокування:** Guard: {sanitized_summary['guard_blocks']}, "
            f"Critic: {sanitized_summary['critic_blocks']}, "
            f"Policy: {sanitized_summary['policy_blocks']}"
        ),
        (
            f"- **Швидкість:** середній час {sanitized_summary['avg_ms']:.0f} мс "
            f"(p95: {sanitized_summary['p95_ms']:.0f} мс)"
        ),
        f"- **LLM навантаження:** {sanitized_summary['avg_llm_calls']:.1f} викликів/звернення\n",
        "## Результати сценаріїв\n",
        "| # | Сценарій | Очікувалось | Отримано | Blocked by | LLM | Час (мс) | Статус |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for idx, r in enumerate(sanitized_results, 1):
        st = "✓ PASS" if r["passed"] else "✕ FAIL"
        row = (
            f"| {idx} | `{r['id']}` | `{r.get('expected_decision', '')}` | "
            f"`{r.get('actual_decision', '')}` | {r.get('blocked_by') or '—'} | "
            f"{r.get('llm_calls', 0)} | {r.get('duration_ms', 0)} | **{st}** |"
        )
        md_content.append(row)

    # Details for failed scenarios and traces
    md_content.append("\n## Детальний огляд сценаріїв\n")
    for r in sanitized_results:
        md_content.append(f"### {r['id']}")
        md_content.append(f"- **Теги:** `{r.get('tags', [])}`")
        md_content.append(f"- **Результат:** {'PASS' if r['passed'] else 'FAIL'}")
        if r.get("errors"):
            md_content.append("- **Помилки перевірки:**")
            for err in r["errors"]:
                md_content.append(f"  - ⚠️ {err}")
        md_content.append(f"- **Фінальна відповідь:** {r.get('reply', '')}")
        md_content.append("<details><summary>Повний trace оркестрації</summary>\n")
        md_content.append("```json")
        md_content.append(json.dumps(r.get("trace", []), ensure_ascii=False, indent=2))
        md_content.append("```\n</details>\n")

    md_path.write_text("\n".join(md_content), encoding="utf-8")
    return json_path, md_path
