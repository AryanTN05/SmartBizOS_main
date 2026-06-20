import json
from datetime import date, datetime, timedelta
from lara_smartbiz.db.connection import SessionLocal
from lara_smartbiz.db.models import Report

def get_report(period: str = "latest", specific_date: str = None):
    db = SessionLocal()
    try:
        query = db.query(Report)
        
        if specific_date:
            target_date = datetime.strptime(specific_date, "%Y-%m-%d").date()
            query = query.filter(Report.period_start <= target_date, Report.period_end >= target_date)
        elif period == "latest":
            query = query.order_by(Report.created_at.desc())
        
        report = query.first()
        
        if not report:
            return json.dumps({"error": "No report found for the specified period."})
            
        return json.dumps({
            "id": report.id,
            "period_start": str(report.period_start),
            "period_end": str(report.period_end),
            "new_leads": report.new_leads,
            "qualified": report.qualified,
            "emails_sent": report.emails_sent,
            "open_rate": report.open_rate,
            "narrative": report.narrative,
            "raw_data": report.raw_data
        })
    finally:
        db.close()

def generate_report():
    # In a real app this would aggregate data from leads/emails tables.
    # For local testing we just create a dummy report.
    db = SessionLocal()
    try:
        new_report = Report(
            period_start=date.today() - timedelta(days=7),
            period_end=date.today(),
            new_leads=10,
            qualified=2,
            emails_sent=50,
            open_rate=0.2,
            narrative="Generated report showing steady progress.",
            raw_data={"generated": True}
        )
        db.add(new_report)
        db.commit()
        db.refresh(new_report)
        
        return json.dumps({
            "message": "Report generated successfully.",
            "report_id": new_report.id
        })
    finally:
        db.close()

def compare_reports(period_a_start: str, period_b_start: str):
    db = SessionLocal()
    try:
        date_a = datetime.strptime(period_a_start, "%Y-%m-%d").date()
        date_b = datetime.strptime(period_b_start, "%Y-%m-%d").date()
        
        report_a = db.query(Report).filter(Report.period_start <= date_a, Report.period_end >= date_a).first()
        report_b = db.query(Report).filter(Report.period_start <= date_b, Report.period_end >= date_b).first()
        
        return json.dumps({
            "report_a": {
                "period_start": str(report_a.period_start),
                "new_leads": report_a.new_leads,
                "qualified": report_a.qualified
            } if report_a else None,
            "report_b": {
                "period_start": str(report_b.period_start),
                "new_leads": report_b.new_leads,
                "qualified": report_b.qualified
            } if report_b else None
        })
    finally:
        db.close()
