import json
from datetime import datetime

def schedule_meeting(name: str, email: str, date: str, time: str, duration_minutes: int = 30):
    """
    Mock integration for scheduling a meeting via Cal.com or similar calendar system.
    """
    # In a real app, this would use httpx to POST to Cal.com API
    # For now, we mock the success response.
    
    return json.dumps({
        "status": "success",
        "message": f"Meeting successfully scheduled with {name} ({email}) on {date} at {time} for {duration_minutes} minutes.",
        "meeting_link": f"https://meet.smartbiz.com/{name.lower().replace(' ', '-')}",
        "date": date,
        "time": time
    })
