import json
from lara_smartbiz.db.connection import SessionLocal
from lara_smartbiz.db.models import Invoice

def get_invoices(status: str = None, vendor: str = None, period: str = None):
    db = SessionLocal()
    try:
        query = db.query(Invoice)
        
        if status:
            query = query.filter(Invoice.status == status)
        if vendor:
            query = query.filter(Invoice.vendor.ilike(f"%{vendor}%"))
            
        invoices = query.order_by(Invoice.due_date.desc()).all()
        result = []
        for inv in invoices:
            result.append({
                "id": inv.id,
                "vendor": inv.vendor,
                "amount": str(inv.amount),
                "currency": inv.currency,
                "status": inv.status,
                "due_date": str(inv.due_date),
                "category": inv.category
            })
            
        return json.dumps(result)
    finally:
        db.close()

def get_spend_summary():
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).all()
        total_spent = sum(float(inv.amount) for inv in invoices if inv.status == "paid")
        total_pending = sum(float(inv.amount) for inv in invoices if inv.status == "pending")
        total_overdue = sum(float(inv.amount) for inv in invoices if inv.status == "overdue")
        
        return json.dumps({
            "total_spent_paid": total_spent,
            "total_pending": total_pending,
            "total_overdue": total_overdue
        })
    finally:
        db.close()
