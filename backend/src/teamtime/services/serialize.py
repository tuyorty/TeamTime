"""ParseResult ↔ JSON для хранения в ``parse_results`` и показа в инбоксе."""

from __future__ import annotations

from typing import Any

from teamtime.parsing import DailyData, Issue, ParseResult, ScheduleData


def issue_to_json(issue: Issue) -> dict[str, Any]:
    return {
        "code": issue.code,
        "severity": issue.severity.value,
        "message": issue.message,
        "line_no": issue.line_no,
        "line": issue.line,
    }


def schedule_to_json(s: ScheduleData) -> dict[str, Any]:
    return {
        "sprint_start": s.sprint_start.isoformat(),
        "sprint_end": s.sprint_end.isoformat(),
        "iso_year": s.iso_year,
        "iso_week": s.iso_week,
        "person": {"raw": s.person.raw, "surname": s.person.surname, "initials": s.person.initials}
        if s.person
        else None,
        "days": [
            {
                "date": d.date.isoformat(),
                "weekday": d.weekday,
                "kind": d.kind.value,
                "intervals": [[i.start, i.end] for i in d.intervals],
                "note": d.note,
                "note_has_time": d.note_has_time,
                "line_no": d.line_no,
            }
            for d in s.days
        ],
        "tasks": list(s.tasks),
    }


def daily_to_json(d: DailyData) -> dict[str, Any]:
    return {
        "work_date": d.work_date.isoformat(),
        "intervals": [[i.start, i.end] for i in d.intervals],
        "efficiency": d.efficiency,
        "tasks": list(d.tasks),
        "worked_sec": d.worked_seconds,
    }


def result_to_json(result: ParseResult) -> dict[str, Any] | None:
    if result.schedule is not None:
        return schedule_to_json(result.schedule)
    if result.daily is not None:
        return daily_to_json(result.daily)
    return None
