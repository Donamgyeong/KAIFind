"""Read-only expiry boundary helpers for current and future report APIs."""


def report_is_open(report, now):
    return report.status == 'OPEN' and report.expires_at > now


def effective_report_status(report, now):
    if report.status == 'OPEN' and report.expires_at <= now:
        return 'CLOSED'
    return report.status
