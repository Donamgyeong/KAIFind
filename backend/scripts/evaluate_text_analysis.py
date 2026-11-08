"""Evaluate synthetic fixtures with the real resident model; no database access."""
import argparse
import asyncio
import json
import math
from pathlib import Path
import resource
import statistics
import time

from library.text_analysis_types import AnalysisError, AnalysisInput
from library.text_input import needs_translation
from library.translation_runtime import TranslationRuntime, TranslationSettings


def rss_kib():
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):
            return int(line.split()[1])
    return None


async def evaluate(settings, samples, repeats):
    runtime = TranslationRuntime(settings)
    before = rss_kib()
    started = time.perf_counter()
    try:
        await runtime.start()
        report = {
            'profile': runtime.profile, 'load_seconds': time.perf_counter() - started,
            'rss_before_kib': before, 'rss_loaded_kib': rss_kib(), 'cases': [],
        }
        durations, translation_durations = [], []
        matched = expected_count = 0
        for sample in samples:
            value = AnalysisInput(description=sample['description'], title=sample.get('title'))
            outcomes = []
            case = {'name': sample['name']}
            expected = set(sample.get('expected_keywords', []))
            expected_count += len(expected)
            for _ in range(repeats):
                started = time.perf_counter()
                try:
                    result = await runtime.analyze(value)
                    outcomes.append(result)
                    elapsed = time.perf_counter() - started
                    durations.append(elapsed)
                    if any(needs_translation(field) for field in (value.description, value.title or '')):
                        translation_durations.append(elapsed)
                except AnalysisError as exc:
                    case['error_code'] = exc.code
                    case['expected_rejection'] = exc.code == sample.get('expected_error')
                    break
            if outcomes and 'error_code' not in case:
                result = outcomes[0]
                found = set(result.keywords)
                matched += len(expected & found)
                case.update(
                    language=result.source_language, keywords=list(result.keywords),
                    translated_text=json.loads(result.translated_text),
                    missing_keywords=sorted(expected - found),
                    forbidden_keywords_found=sorted(set(sample.get('forbidden_keywords', [])) & found),
                    repeat_equal=all(outcome == result for outcome in outcomes),
                )
            case['rss_kib'] = rss_kib()
            report['cases'].append(case)
        report['latency_p50_seconds'] = statistics.median(durations) if durations else None
        report['latency_p95_seconds'] = sorted(durations)[math.ceil(len(durations) * .95) - 1] if durations else None
        report['translation_p50_seconds'] = statistics.median(translation_durations) if translation_durations else None
        report['translation_p95_seconds'] = (
            sorted(translation_durations)[math.ceil(len(translation_durations) * .95) - 1]
            if translation_durations else None
        )
        report['expected_keyword_recall'] = matched / expected_count if expected_count else None
        report['rss_after_kib'] = rss_kib()
        report['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report['load_count'] = runtime.load_count
        report['case_count'] = len(samples)
        report['expected_rejections'] = sum(case.get('expected_rejection', False) for case in report['cases'])
        report['failed_cases'] = sum(
            ('error_code' in case and not case.get('expected_rejection'))
            or (sample.get('expected_error') is not None and 'error_code' not in case)
            for case, sample in zip(report['cases'], samples)
        )
        return report
    finally:
        await runtime.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', type=Path, default=Path('tests/data/text_analysis_samples.json'))
    parser.add_argument('--output', type=Path, default=Path('/app/.cache/text-analysis-evaluation.json'))
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error('--repeats must be between 1 and 20')
    report = asyncio.run(evaluate(
        TranslationSettings.from_environment(), json.loads(args.samples.read_text()), args.repeats,
    ))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    profile_path = args.output.with_name(args.output.stem + '-profile.json')
    profile_path.write_text(json.dumps(report['profile'], ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key not in {'profile', 'cases'}}))
    print(f'Evaluation report saved: {args.output}')
    if report['failed_cases'] or any(
        case.get('repeat_equal') is False or case.get('forbidden_keywords_found')
        for case in report['cases']
    ):
        raise SystemExit('Evaluation found runtime, consistency or negation failures; inspect the report')


if __name__ == '__main__':
    main()
